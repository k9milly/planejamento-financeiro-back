"""Testes dos leitores de planilha (CSV e XLSX) — ADR-08.

O que importa aqui é o que muda em relação ao OFX: não existe identificador de
transação vindo do banco, e o arquivo é escrito por gente/Excel, então valor e
data chegam em formas que o OFX nunca produz.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest

from app.services.extrato import ErroExtrato
from app.services.tabular import ErroTabular, ler_csv, ler_xlsx

CSV = (
    "data;valor;descricao\n"
    "2026-08-05;-113,85;CLAUDE AI SUBSCRIPTION\n"
    "05/08/2026;-47.00;IFOOD RESTAURANTE\n"
    "2026-08-07;2000,00;SALARIO\n"
).encode("utf-8")


def planilha(linhas: list[list[object]]) -> bytes:
    """Monta um .xlsx de verdade em memória, sem arquivo de fixture no repo."""
    import openpyxl

    livro = openpyxl.Workbook()
    for linha in linhas:
        livro.active.append(linha)
    buffer = io.BytesIO()
    livro.save(buffer)
    return buffer.getvalue()


XLSX = planilha(
    [
        ["data", "valor", "descricao"],
        [date(2026, 8, 5), -113.85, "CLAUDE AI SUBSCRIPTION"],
        [date(2026, 8, 7), 2000, "SALARIO"],
    ]
)


class TestCSV:
    def test_le_as_tres_transacoes(self):
        assert len(ler_csv(CSV)) == 3

    def test_sinal_define_o_sentido(self):
        por_descricao = {t.descricao: t for t in ler_csv(CSV)}

        saida = por_descricao["CLAUDE AI SUBSCRIPTION"]
        assert saida.saida is True
        assert saida.valor == Decimal("113.85")

        entrada = por_descricao["SALARIO"]
        assert entrada.saida is False
        assert entrada.valor == Decimal("2000.00")

    def test_aceita_os_dois_formatos_de_data(self):
        datas = {t.data for t in ler_csv(CSV)}
        assert datas == {date(2026, 8, 5), date(2026, 8, 7)}

    def test_ordem_das_colunas_e_livre(self):
        trocado = b"DESCRICAO,Data,VALOR\nMERCADO,2026-08-05,-30,00\n"
        transacao = ler_csv(trocado)[0]
        assert transacao.descricao == "MERCADO"
        assert transacao.valor == Decimal("30.00")

    def test_cabecalho_com_acento_e_maiuscula(self):
        com_acento = "Data;Valor;Descrição\n2026-08-05;-30,00;MERCADO\n".encode("utf-8")
        assert ler_csv(com_acento)[0].descricao == "MERCADO"

    def test_pula_o_preambulo_antes_do_cabecalho(self):
        conteudo = (
            "Extrato de conta corrente\n"
            "Periodo: 01/08/2026 a 31/08/2026\n"
            "\n"
            "data;valor;descricao\n"
            "2026-08-05;-30,00;MERCADO\n"
        ).encode("utf-8")
        assert len(ler_csv(conteudo)) == 1

    def test_separador_de_milhar_com_virgula_decimal(self):
        conteudo = 'data;valor;descricao\n2026-08-05;"R$ -1.234,56";ALUGUEL\n'.encode()
        assert ler_csv(conteudo)[0].valor == Decimal("1234.56")

    def test_separador_de_milhar_com_ponto_decimal(self):
        conteudo = b'data,valor,descricao\n2026-08-05,"-1,234.56",ALUGUEL\n'
        assert ler_csv(conteudo)[0].valor == Decimal("1234.56")

    def test_valor_zero_e_ignorado(self):
        conteudo = b"data;valor;descricao\n2026-08-05;0;ESTORNO\n2026-08-06;-10;X\n"
        assert len(ler_csv(conteudo)) == 1

    def test_linha_em_branco_nao_atrapalha(self):
        conteudo = b"data;valor;descricao\n\n2026-08-05;-10;X\n\n"
        assert len(ler_csv(conteudo)) == 1

    def test_bom_do_excel_nao_quebra_o_cabecalho(self):
        conteudo = "data;valor;descricao\n2026-08-05;-10;X\n".encode("utf-8-sig")
        assert len(ler_csv(conteudo)) == 1

    def test_acento_em_latin1(self):
        conteudo = "data;valor;descricao\n2026-08-05;-10;PADARIA JOÃO\n".encode(
            "latin-1"
        )
        assert ler_csv(conteudo)[0].descricao == "PADARIA JOÃO"

    def test_ordena_por_data(self):
        conteudo = b"data;valor;descricao\n2026-08-09;-10;B\n2026-08-01;-10;A\n"
        assert [t.descricao for t in ler_csv(conteudo)] == ["A", "B"]


class TestErrosDoCSV:
    def test_sem_as_colunas_esperadas(self):
        with pytest.raises(ErroTabular, match="colunas"):
            ler_csv(b"quando;quanto;o que\n2026-08-05;-10;X\n")

    def test_arquivo_que_nao_e_planilha(self):
        with pytest.raises(ErroTabular):
            ler_csv(b"nao sou um extrato")

    def test_data_ilegivel_cita_a_linha(self):
        conteudo = b"data;valor;descricao\n2026-08-05;-10;OK\n05-08-26;-10;RUIM\n"
        with pytest.raises(ErroTabular, match="linha 3"):
            ler_csv(conteudo)

    def test_valor_ilegivel_cita_a_linha(self):
        conteudo = b"data;valor;descricao\n2026-08-05;dez reais;X\n"
        with pytest.raises(ErroTabular, match="linha 2"):
            ler_csv(conteudo)

    def test_cabecalho_sozinho_e_recusado(self):
        with pytest.raises(ErroTabular, match="Nenhuma transação"):
            ler_csv(b"data;valor;descricao\n")

    def test_erro_e_um_erro_de_extrato(self):
        """O roteador captura `ErroExtrato`; se a herança quebrar, vira 500."""
        with pytest.raises(ErroExtrato):
            ler_csv(b"nao sou um extrato")


class TestXLSX:
    def test_le_data_e_numero_nativos_da_planilha(self):
        transacoes = ler_xlsx(XLSX)
        assert [t.data for t in transacoes] == [date(2026, 8, 5), date(2026, 8, 7)]
        assert transacoes[0].valor == Decimal("113.85")
        assert transacoes[0].saida is True
        assert transacoes[1].valor == Decimal("2000.00")
        assert transacoes[1].saida is False

    def test_celulas_como_texto_tambem_funcionam(self):
        conteudo = planilha(
            [["data", "valor", "descricao"], ["05/08/2026", "-30,00", "MERCADO"]]
        )
        assert ler_xlsx(conteudo)[0].valor == Decimal("30.00")

    def test_arquivo_que_nao_e_xlsx(self):
        with pytest.raises(ErroTabular, match="xlsx"):
            ler_xlsx(CSV)


class TestIdentificador:
    def test_e_estavel_entre_leituras(self):
        assert [t.fitid for t in ler_csv(CSV)] == [t.fitid for t in ler_csv(CSV)]

    def test_o_mesmo_extrato_em_csv_e_xlsx_gera_o_mesmo_identificador(self):
        """Baixar o extrato nos dois formatos não pode virar lançamento em dobro."""
        linhas = [["data", "valor", "descricao"], ["2026-08-05", "-113,85", "CLAUDE"]]
        em_csv = b"data;valor;descricao\n2026-08-05;-113,85;CLAUDE\n"
        assert ler_csv(em_csv)[0].fitid == ler_xlsx(planilha(linhas))[0].fitid

    def test_entrada_e_saida_do_mesmo_valor_nao_colidem(self):
        conteudo = b"data;valor;descricao\n2026-08-05;-50;PIX\n2026-08-05;50;PIX\n"
        primeiro, segundo = ler_csv(conteudo)
        assert primeiro.fitid != segundo.fitid

    def test_descricoes_diferentes_geram_identificadores_diferentes(self):
        conteudo = b"data;valor;descricao\n2026-08-05;-50;PADARIA\n2026-08-05;-50;UBER\n"
        primeiro, segundo = ler_csv(conteudo)
        assert primeiro.fitid != segundo.fitid
