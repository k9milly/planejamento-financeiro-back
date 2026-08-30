"""Leitores de extrato em planilha: CSV e XLSX.

Ao contrário do OFX, que é um formato de fato — com tags padronizadas e um
identificador de transação —, não existe "CSV de banco padrão": cada banco
exporta as colunas que quer, na ordem que quer. Então o layout aceito aqui é
um formato **da própria aplicação**, deliberadamente mínimo (ver ADR-08):

* três colunas identificadas **pelo nome do cabeçalho**, em qualquer ordem:
  `data`, `valor`, `descricao` (acentos e maiúsculas são ignorados);
* `valor` com sinal, na mesma convenção do OFX — negativo é saída, positivo é
  entrada;
* `data` em `AAAA-MM-DD` ou `DD/MM/AAAA`.

Se o extrato de um banco específico usar outros nomes de coluna, o ajuste é
mapear nomes aqui dentro: nada fora deste módulo sabe como o arquivo é feito.

Erros aqui são **ruidosos de propósito**. O leitor de OFX pula em silêncio uma
transação sem data ou sem valor, porque nesse formato isso é uma anomalia de
uma linha isolada. Numa planilha, uma data ilegível quase sempre significa que
a coluna inteira está num formato que não foi previsto — descartar em silêncio
importaria meio extrato sem ninguém perceber. Por isso a linha do problema é
citada na mensagem.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.services.extrato import (
    ErroExtrato,
    TransacaoExtrato,
    identificador_sintetico,
)

COLUNAS = ("data", "valor", "descricao")

# Quantas linhas procurar até desistir de achar o cabeçalho. Alguns exports
# trazem título, CNPJ e período antes dele; passando muito disso, o arquivo
# provavelmente não é um extrato no layout esperado.
LINHAS_ATE_O_CABECALHO = 20

_DELIMITADORES = (";", ",", "\t")


class ErroTabular(ErroExtrato):
    """Planilha ilegível, sem as colunas esperadas, ou sem transações."""


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento e sem espaço sobrando — para casar cabeçalhos."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    limpo = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(limpo.split()).lower()


def _texto(celula: object) -> str:
    return "" if celula is None else str(celula).strip()


def _achar_cabecalho(linhas: list[list[object]]) -> tuple[int, dict[str, int]]:
    """Índice da linha de cabeçalho e a posição de cada coluna nela."""
    for numero, linha in enumerate(linhas[:LINHAS_ATE_O_CABECALHO]):
        nomes = {_normalizar(_texto(c)): i for i, c in enumerate(linha)}
        if all(coluna in nomes for coluna in COLUNAS):
            return numero, {coluna: nomes[coluna] for coluna in COLUNAS}

    raise ErroTabular(
        "Não encontrei as colunas data, valor e descricao no cabeçalho. "
        "A planilha precisa ter essas três colunas (a ordem não importa)."
    )


def _para_data(bruto: object, linha: int) -> date:
    if isinstance(bruto, datetime):
        return bruto.date()
    if isinstance(bruto, date):
        return bruto

    texto = _texto(bruto)
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue

    raise ErroTabular(
        f"Data inválida na linha {linha}: {texto!r}. "
        "Use AAAA-MM-DD ou DD/MM/AAAA."
    )


def _para_valor(bruto: object, linha: int) -> Decimal:
    """Valor com sinal. Aceita o que uma planilha brasileira costuma trazer.

    Vem número de verdade no XLSX e texto no CSV, e no texto pode haver `R$`,
    separador de milhar e vírgula decimal — `-1.234,56` e `-1234.56` significam
    a mesma coisa e as duas formas aparecem na prática.
    """
    if isinstance(bruto, (int, float, Decimal)):
        return Decimal(str(bruto)).quantize(Decimal("0.01"))

    texto = _texto(bruto)
    limpo = re.sub(r"[^\d,.\-]", "", texto)

    # Quem estiver mais à direita é o separador decimal; o outro é milhar.
    if "," in limpo and "." in limpo:
        decimal_e_virgula = limpo.rfind(",") > limpo.rfind(".")
        limpo = (
            limpo.replace(".", "").replace(",", ".")
            if decimal_e_virgula
            else limpo.replace(",", "")
        )
    elif "," in limpo:
        limpo = limpo.replace(",", ".")

    try:
        return Decimal(limpo).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as erro:
        raise ErroTabular(f"Valor inválido na linha {linha}: {texto!r}.") from erro


def _transacoes(linhas: list[list[object]]) -> list[TransacaoExtrato]:
    inicio, colunas = _achar_cabecalho(linhas)

    transacoes: list[TransacaoExtrato] = []
    for deslocamento, linha in enumerate(linhas[inicio + 1 :]):
        numero = inicio + deslocamento + 2  # 1-indexado, como a planilha mostra

        if not any(_texto(celula) for celula in linha):
            continue  # linha em branco: separador visual ou sobra do export

        def celula(coluna: str, linha=linha) -> object:
            posicao = colunas[coluna]
            return linha[posicao] if posicao < len(linha) else None

        valor = _para_valor(celula("valor"), numero)
        if valor == 0:
            continue  # estornos casados que se anulam não viram lançamento

        quando = _para_data(celula("data"), numero)
        descricao = " ".join(_texto(celula("descricao")).split())

        transacoes.append(
            TransacaoExtrato(
                # Planilha nunca traz identificador de transação — sempre o
                # sintético, o mesmo que o OFX sem FITID usa.
                fitid=identificador_sintetico(quando, valor, descricao),
                data=quando,
                valor=abs(valor),
                saida=valor < 0,
                descricao=descricao,
            )
        )

    if not transacoes:
        raise ErroTabular(
            "Nenhuma transação encontrada. O cabeçalho está certo, mas não há "
            "nenhuma linha com valor diferente de zero abaixo dele."
        )

    return sorted(transacoes, key=lambda t: t.data)


def _decodificar(conteudo: bytes) -> str:
    """UTF-8 quando dá, Latin-1 como rede de segurança.

    `utf-8-sig` porque o Excel escreve BOM ao salvar como CSV, e sem descartá-lo
    o primeiro cabeçalho viraria `\\ufeffdata` e não casaria com `data`.
    """
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


def _delimitador(texto: str) -> str:
    """O separador mais frequente na primeira linha não vazia.

    `csv.Sniffer` erra justamente no caso brasileiro mais comum — vírgula
    decimal com separador `;` —, então a contagem direta é mais confiável aqui.
    """
    primeira = next((linha for linha in texto.splitlines() if linha.strip()), "")
    return max(_DELIMITADORES, key=primeira.count)


def ler_csv(conteudo: bytes) -> list[TransacaoExtrato]:
    texto = _decodificar(conteudo)
    leitor = csv.reader(io.StringIO(texto), delimiter=_delimitador(texto))
    return _transacoes([list(linha) for linha in leitor])


def ler_xlsx(conteudo: bytes) -> list[TransacaoExtrato]:
    # Import local: openpyxl carrega devagar e só faz falta em quem importa
    # planilha, não em toda subida do servidor.
    import openpyxl

    try:
        planilha = openpyxl.load_workbook(
            io.BytesIO(conteudo), data_only=True, read_only=True
        )
    except Exception as erro:  # openpyxl levanta de tudo em arquivo corrompido
        raise ErroTabular(
            "Não consegui abrir a planilha. Confira se o arquivo é mesmo um "
            ".xlsx (o formato antigo .xls não é aceito)."
        ) from erro

    try:
        aba = planilha.worksheets[0]
        linhas = [list(linha) for linha in aba.iter_rows(values_only=True)]
    finally:
        planilha.close()

    return _transacoes(linhas)
