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
PERFIS = (
    ("Mercado Pago", ("EXTRATO DE CONTA", "ID DA OPERACAO"), _le_mercado_pago),
    ("Nubank", ("NUBANK.COM.BR",), _le_nubank),
)


def _sem_acento(texto: str) -> str:
    import unicodedata

    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).upper()


def _perfil(texto: str):
    procuravel = _sem_acento(texto)
    for nome, assinaturas, leitor in PERFIS:
        if all(a in procuravel for a in assinaturas):
            return nome, leitor
    return None, None


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

    nome, leitor = _perfil("\n".join(linhas))
    if leitor is None:
        raise ErroPDF(
            "Não reconheço o layout deste PDF. Cada banco organiza o extrato de "
            "um jeito, e hoje sei ler os do Nubank e do Mercado Pago. Para os "
            "outros, use OFX, CSV ou XLSX — são formatos feitos para serem "
            "lidos, e o resultado é exato."
        )

    brutas = leitor(linhas)
    if not brutas:
        raise ErroPDF(
            f"Reconheci este PDF como extrato do {nome}, mas não encontrei "
            "nenhum lançamento nele. Se o arquivo não estiver vazio, o layout "
            "do banco pode ter mudado."
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
            )
            for bruta in brutas
        ),
        key=lambda t: t.data,
    )
