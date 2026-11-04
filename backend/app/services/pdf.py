"""Leitor de extrato em PDF.

PDF é o formato mais hostil dos quatro, e por um motivo que não dá para
contornar: **ele descreve como desenhar uma página, não o que a página
significa.** Não existe "coluna valor" num PDF — existe um texto numa
coordenada.

A primeira versão deste leitor tentou um padrão único, genérico: linha que
começa com data e termina com valor. Os dois extratos reais da Kamilly
reprovaram a ideia, cada um de um jeito, e a lição foi a mesma: **não existe
layout genérico de extrato em PDF.** Por isso aqui há *perfis* — um por banco
conhecido — e um erro claro quando nenhum reconhece o arquivo.

Recusar o desconhecido é deliberado. Um leitor genérico erraria calado no
Mercado Pago, onde cada linha traz **dois** valores (o da transação e o saldo
corrente); pegar o último importaria o saldo no lugar do lançamento, com
número plausível e errado. Melhor dizer "não conheço este layout" do que
inventar.

O que os perfis têm em comum, e que nenhum regex de uma linha resolve:

* a linha **quebra** no meio da transação — a data pode estar sozinha numa
  linha, e a descrição continuar na seguinte;
* a maior parte do texto do documento nunca foi transação (cabeçalho,
  endereço, aviso legal), então linha não reconhecida é ignorada em silêncio.

A proteção contra ignorar demais é o fluxo, não o leitor: a prévia mostra
`total_lidas` e nada é gravado até a confirmação.

`pypdf` e não `pdfplumber`: wheel pura, 395 KB, sem dependência. O pdfplumber
daria a posição de cada palavra, mas traria `cryptography`, `pillow`, `cffi` e
`pypdfium2` junto — dezenas de megabytes de binário num contêiner que hoje não
tem nada disso.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.extrato import (
    ErroExtrato,
    TransacaoExtrato,
    identificador_sintetico,
    para_decimal,
)


class ErroPDF(ErroExtrato):
    """PDF ilegível, sem texto, ou de um banco cujo layout não é conhecido."""


# Valor monetário **com centavos**. Exigir os centavos não é capricho: sem
# isso, `Conta: 4100275488-6` e `CNPJ: 30.680.829/0001-43` viram valores, e o
# documento passa a ter transações que nunca existiram.
_VALOR = r"-?\s*[\d.]*\d,\d{2}"

MESES = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}


@dataclass
class Bruta:
    """Uma transação já reconhecida, antes de virar `TransacaoExtrato`."""

    data: date
    descricao: str
    valor: Decimal  # com sinal
    identificador: str | None = None


# --------------------------------------------------------------------------- #
# Mercado Pago — "EXTRATO DE CONTA"
# --------------------------------------------------------------------------- #
# Layout: data, descrição, ID da operação, valor, saldo. A linha fecha sempre
# com os dois valores em `R$`, precedidos pelo ID.
_MP_DATA = re.compile(r"^(\d{2})-(\d{2})-(\d{4})\b")
_MP_FECHA = re.compile(
    rf"(?P<id>\d{{8,}})\s+R\$\s*(?P<valor>{_VALOR})\s+R\$\s*{_VALOR}\s*$"
)


def _le_mercado_pago(linhas: list[str]) -> list[Bruta]:
    achadas: list[Bruta] = []
    data_atual: date | None = None
    acumulado: list[str] = []

    for linha in linhas:
        texto = linha.strip()
        if not texto or texto.startswith("Data Descrição"):
            continue

        if achado_data := _MP_DATA.match(texto):
            dia, mes, ano = (int(g) for g in achado_data.groups())
            data_atual = date(ano, mes, dia)
            texto = texto[achado_data.end() :].strip()
            acumulado = []

        fecha = _MP_FECHA.search(texto)
        if fecha is None:
            if texto:
                acumulado.append(texto)
            continue

        valor = para_decimal(fecha["valor"])
        if data_atual is None or valor is None or valor == 0:
            acumulado = []
            continue

        descricao = " ".join((" ".join(acumulado) + " " + texto[: fecha.start()]).split())
        achadas.append(Bruta(data_atual, descricao, valor, fecha["id"]))
        acumulado = []

    return achadas


# --------------------------------------------------------------------------- #
# Mercado Pago — fatura do cartão de crédito
# --------------------------------------------------------------------------- #
# Documento diferente do extrato em quase tudo, e o que mais importa:
#
# * **a data não tem ano** — é `08/09`, dia e mês. O ano sai da data de
#   emissão da fatura, pela regra do `_data_da_fatura` abaixo;
# * não há identificador de operação, ao contrário do extrato;
# * as transações vêm agrupadas por cartão (há dois no mesmo PDF), e cada
#   grupo fecha com uma linha `Total` que **não** é transação;
# * a primeira página é resumo e propaganda, cheia de valores em reais (total
#   a pagar, pagamento mínimo, simulações de parcelamento) que virariam
#   compras fantasmas se entrassem.
#
# O mesmo corte resolve os três últimos: só é transação a linha que
# **começa** com `dd/mm`. Total, resumo e propaganda não começam.
_FAT_REFERENCIA = re.compile(
    r"(?:Emitida em|Vencimento)\s*:?\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE
)
# O `\s+` não é decorativo: é ele que separa `08/09 COMPRA` de `13/10/2026`.
# Numa data completa o caractere seguinte ao mês é `/`, não espaço, então a
# linha não casa. Com `\s*` no lugar, o vencimento viraria uma compra com o
# valor que estivesse ao lado — na fatura, o total a pagar.
_FAT_DATA = re.compile(r"^(\d{2})/(\d{2})\s+(?P<resto>.*)$")
_FAT_FECHA = re.compile(rf"^(?P<resto>.*?)\s*R\$\s*(?P<valor>{_VALOR})\s*$")
# Fronteiras de seção. Não é isto que mantém a linha `Total` fora da
# importação — disso cuida a âncora `dd/mm`, que `Total R$ 292,25` não tem.
# Isto resolve o caso estreito e feio: uma compra cuja descrição quebrou e
# **não** fechou com valor deixa uma transação pendente, e sem o corte ela
# captura o valor da próxima linha — que é justamente o total do cartão.
_FAT_CORTA = re.compile(r"^(Total\b|Cart[ãa]o\b|Data\s+Movimenta)", re.IGNORECASE)


def _referencia_da_fatura(linhas: list[str]) -> date | None:
    """Data de emissão da fatura — ou, na falta dela, a de vencimento."""
    for linha in linhas:
        if achado := _FAT_REFERENCIA.search(linha):
            dia, mes, ano = (int(g) for g in achado.groups())
            try:
                return date(ano, mes, dia)
            except ValueError:
                continue
    return None


def _data_da_fatura(dia: int, mes: int, referencia: date) -> date | None:
    """Devolve o ano que falta na linha da transação.

    A compra é sempre **anterior** à emissão da fatura — é o que a torna parte
    desta fatura. Então: tenta o ano da referência e, se a data cair no futuro,
    é do ano anterior.

    Resolve os dois casos reais de uma vez: a parcela de `26/07` numa fatura de
    outubro fica em julho do mesmo ano, e um `20/12` numa fatura emitida em
    janeiro volta para dezembro do ano passado — que o "usa o ano da fatura"
    ingênuo jogaria onze meses para a frente.
    """
    for ano in (referencia.year, referencia.year - 1):
        try:
            candidata = date(ano, mes, dia)
        except ValueError:
            continue  # 29/02 em ano comum; o ano anterior pode servir
        if candidata <= referencia:
            return candidata
    return None


def _identificar_compras(brutas: list[Bruta]) -> None:
    """Dá a cada compra uma chave estável, já que a fatura não traz nenhuma.

    OFX sem `FITID`, CSV e XLSX caem no `identificador_sintetico` (data, valor
    e descrição). Aqui isso não basta: numa fatura é normal passar o cartão
    **duas vezes no mesmo dia, no mesmo lugar, pelo mesmo valor** — duas idas à
    farmácia — e as duas linhas colidiriam numa só, com a segunda descartada
    como duplicata. Perder lançamento em silêncio é exatamente o que este
    leitor existe para não fazer.

    O desempate é a ordem de aparição no documento, e é estável porque uma
    fatura é documento fechado: baixada de novo, vem na mesma ordem, e a
    reimportação reconhece tudo como já importado.
    """
    vistas: dict[tuple[str, Decimal], int] = {}
    for bruta in brutas:
        base = f"fatura|{bruta.data.isoformat()}|{bruta.descricao[:40]}"
        chave = (base, bruta.valor)
        ocorrencia = vistas[chave] = vistas.get(chave, 0) + 1
        bruta.identificador = base if ocorrencia == 1 else f"{base}#{ocorrencia}"


def _le_mercado_pago_fatura(linhas: list[str]) -> list[Bruta]:
    referencia = _referencia_da_fatura(linhas)
    if referencia is None:
        raise ErroPDF(
            "Reconheci a fatura do cartão Mercado Pago, mas não achei a data "
            "de emissão nem a de vencimento — e sem uma delas não dá para "
            "saber de que ano são as compras, porque na fatura a data vem só "
            "como dia e mês."
        )

    achadas: list[Bruta] = []
    pendente: tuple[int, int, list[str]] | None = None

    def registrar(dia: int, mes: int, descricao: str, valor: Decimal) -> None:
        quando = _data_da_fatura(dia, mes, referencia)
        texto = " ".join(descricao.split())
        if quando is None or not texto or valor == 0:
            return
        # Toda linha da fatura é compra, logo saída. Se a linha trouxer sinal
        # negativo é estorno, e a conta se inverte sozinha.
        achadas.append(Bruta(quando, texto, -valor))

    for linha in linhas:
        texto = linha.strip()
        if not texto:
            continue

        if _FAT_CORTA.match(texto):
            pendente = None
            continue

        if achado_data := _FAT_DATA.match(texto):
            pendente = None
            dia, mes = int(achado_data.group(1)), int(achado_data.group(2))
            fecha = _FAT_FECHA.match(achado_data["resto"])
            if fecha is None:
                # Descrição comprida que quebrou: o valor vem adiante.
                pendente = (dia, mes, [achado_data["resto"]])
                continue
            if (valor := para_decimal(fecha["valor"])) is not None:
                registrar(dia, mes, fecha["resto"], valor)
            continue

        if pendente is None:
            continue

        fecha = _FAT_FECHA.match(texto)
        if fecha is None:
            pendente[2].append(texto)
            continue

        if (valor := para_decimal(fecha["valor"])) is not None:
            dia, mes, partes = pendente
            registrar(dia, mes, " ".join([*partes, fecha["resto"]]), valor)
        pendente = None

    _identificar_compras(achadas)
    return achadas


# --------------------------------------------------------------------------- #
# Nubank — extrato da conta
# --------------------------------------------------------------------------- #
# Layout diferente em tudo: a data vem como "08 AGO 2026", e o **sentido** do
# dinheiro não está na linha da transação — está no cabeçalho do dia, que traz
# "Total de entradas +" ou "Total de saídas -". O valor da transação vem sem
# sinal nenhum.
# `\s.*?` e não `\s+.*?`: os dois casam o mesmo texto, porque o `.*?` já
# absorve espaço — mas com os dois quantificadores disputando os mesmos
# caracteres, o motor tenta todas as divisões possíveis antes de desistir de
# uma linha que não traz "Total de". Numa linha com dois mil espaços isso
# passava de 15 ms para 0 ms ao tirar o `+`. Linha de extrato é curta, então
# nunca doeu aqui; a troca não tem contrapartida (SonarQube python:S8786).
_NU_DIA = re.compile(
    r"^(\d{2})\s+([A-Z]{3})\s+(\d{4})\s.*?Total de (entradas|sa[íi]das)",
    re.IGNORECASE,
)
_NU_FECHA = re.compile(rf"(?P<valor>{_VALOR})\s*$")


def _le_nubank(linhas: list[str]) -> list[Bruta]:
    achadas: list[Bruta] = []
    data_atual: date | None = None
    saida_do_dia = True
    acumulado: list[str] = []

    for linha in linhas:
        texto = linha.strip()
        if not texto:
            continue

        if achado_dia := _NU_DIA.match(texto):
            dia, mes, ano, sentido = achado_dia.groups()
            numero_do_mes = MESES.get(mes.upper())
            if numero_do_mes is None:
                continue
            data_atual = date(int(ano), numero_do_mes, int(dia))
            saida_do_dia = sentido.lower().startswith("sa")
            acumulado = []
            continue

        if data_atual is None:
            continue  # rodapé e cabeçalho, antes de qualquer dia

        fecha = _NU_FECHA.search(texto)
        if fecha is None:
            acumulado.append(texto)
            continue

        valor = para_decimal(fecha["valor"])
        if valor is None or valor == 0:
            acumulado = []
            continue

        descricao = " ".join((" ".join(acumulado) + " " + texto[: fecha.start()]).split())
        if not descricao:
            acumulado = []
            continue

        achadas.append(
            Bruta(data_atual, descricao, -abs(valor) if saida_do_dia else abs(valor))
        )
        acumulado = []

    return achadas


# --------------------------------------------------------------------------- #
# Escolha do perfil
# --------------------------------------------------------------------------- #
# A assinatura é procurada no texto inteiro, sem acento e em maiúsculas.
# O nome é a frase inteira porque entra na mensagem de erro: "reconheci este
# PDF como <nome>, mas não achei lançamento". Dois documentos do mesmo banco
# convivem aqui, então "Mercado Pago" sozinho não diria qual deles.
# O quarto campo diz se o documento é de cartão. Numa fatura toda linha é
# compra no crédito — é o que o documento é — e sem essa marca a confirmação
# recusaria tudo com `422`, porque o ADR-0002 exige `forma_pagamento=credito`
# para saída em conta do tipo cartão.
PERFIS = (
    (
        "extrato do Mercado Pago",
        ("EXTRATO DE CONTA", "ID DA OPERACAO"),
        _le_mercado_pago,
        False,
    ),
    (
        "fatura do cartão Mercado Pago",
        ("DETALHES DE CONSUMO", "MOVIMENTACOES"),
        _le_mercado_pago_fatura,
        True,
    ),
    ("extrato do Nubank", ("NUBANK.COM.BR",), _le_nubank, False),
)


def _sem_acento(texto: str) -> str:
    import unicodedata

    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).upper()


def _perfil(texto: str):
    procuravel = _sem_acento(texto)
    for nome, assinaturas, leitor, no_credito in PERFIS:
        if all(a in procuravel for a in assinaturas):
            return nome, leitor, no_credito
    return None, None, False


def _texto_do_pdf(conteudo: bytes) -> list[str]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        leitor = PdfReader(io.BytesIO(conteudo))
    except (PdfReadError, OSError, ValueError) as erro:
        raise ErroPDF(
            "Não consegui abrir este PDF. Confira se o arquivo não está "
            "corrompido."
        ) from erro

    if leitor.is_encrypted:
        # O extrato do Mercado Pago vem "protegido", mas com senha vazia: é
        # proteção de permissões (impedir edição), não de leitura. Só desiste
        # se a senha vazia não abrir.
        try:
            aberto = leitor.decrypt("")
        except Exception:  # noqa: BLE001
            aberto = 0
        if not aberto:
            raise ErroPDF(
                "Este PDF está protegido por senha. Abra-o, salve uma cópia sem "
                "senha, e importe essa cópia."
            )

    linhas: list[str] = []
    for pagina in leitor.pages:
        try:
            texto = pagina.extract_text() or ""
        except Exception:  # noqa: BLE001 — página quebrada não invalida o resto
            continue
        linhas.extend(texto.splitlines())
    return linhas


def ler_pdf(conteudo: bytes) -> list[TransacaoExtrato]:
    linhas = _texto_do_pdf(conteudo)

    if not any(linha.strip() for linha in linhas):
        raise ErroPDF(
            "Este PDF não tem texto — provavelmente é um documento escaneado, "
            "uma imagem. Não dá para ler os lançamentos dele. Baixe o extrato "
            "em OFX, CSV ou XLSX, que o banco costuma oferecer."
        )

    nome, leitor, no_credito = _perfil("\n".join(linhas))
    if leitor is None:
        raise ErroPDF(
            "Não reconheço o layout deste PDF. Cada banco organiza o documento "
            "de um jeito, e hoje sei ler o extrato do Nubank, o extrato do "
            "Mercado Pago e a fatura do cartão Mercado Pago. Para os outros, "
            "use OFX, CSV ou XLSX — são formatos feitos para serem lidos, e o "
            "resultado é exato."
        )

    brutas = leitor(linhas)
    if not brutas:
        raise ErroPDF(
            f"Reconheci este PDF como {nome}, mas não encontrei nenhum "
            "lançamento nele. Se o arquivo não estiver vazio, o layout do "
            "banco pode ter mudado."
        )

    return sorted(
        (
            TransacaoExtrato(
                # O ID do Mercado Pago é **da operação**, não da transação: um
                # Pix e o estorno dele carregam o mesmo número. Sozinho, ele
                # apagaria um dos dois em silêncio — no extrato de agosto isso
                # eram três pares de R$ 89,00. Com o valor assinado junto, o
                # par se separa e operações de fato repetidas continuam exatas.
                #
                # O ID ainda assim é necessário: o mesmo extrato tem dois "Pix
                # enviado Jose Vieira da Silva" de R$ 89,00 no mesmo dia, que o
                # identificador sintético (data + valor + descrição) juntaria
                # num só. Sem ID, cai no sintético, como CSV e XLSX.
                fitid=(
                    f"{bruta.identificador}|{bruta.valor}"
                    if bruta.identificador
                    else identificador_sintetico(
                        bruta.data, bruta.valor, bruta.descricao
                    )
                ),
                data=bruta.data,
                valor=abs(bruta.valor),
                saida=bruta.valor < 0,
                descricao=bruta.descricao,
                no_credito=no_credito,
            )
            for bruta in brutas
        ),
        key=lambda t: t.data,
    )
