"""Leitor de extrato em PDF, por perfil de banco (ADR-12).

Os PDFs daqui são montados à mão, na função `pdf`, **reproduzindo o texto que
os extratos reais da Kamilly produzem** — copiado da extração dos arquivos de
agosto de 2026, não inventado. Guardar os PDFs reais no repositório está fora
de questão: são dados financeiros dela.

Por isso estes testes provam que o leitor entende **aqueles layouts**, e não
que ele entende os arquivos exatos. A conferência contra os arquivos de
verdade foi feita à parte, somando entradas e saídas e comparando com os
totais que os próprios documentos declaram — ver o ADR-12.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.extrato import ErroExtrato
from app.services.pdf import ErroPDF, ler_pdf


def pdf(linhas: list[str], paginas: int = 1) -> bytes:
    """Monta um PDF de verdade com as linhas dadas, sem dependência extra.

    Limite conhecido: a fonte embutida aqui não carrega todo acento — `ê` sai
    trocado na extração, embora `í` passe. Por isso as fixturas evitam acento
    onde o teste compara texto. Nos arquivos reais os acentos saem corretos, e
    é a conferência contra eles que cobre isso.
    """

    def escapar(linha: str) -> str:
        """Barra e parênteses são sintaxe de string no PDF — precisam de escape.

        Apagá-los seria mais simples e mudaria o texto sob teste: foi o que fez
        o teste do valor entre parênteses passar a testar outra coisa.
        """
        for alvo in ("\\", "(", ")"):
            linha = linha.replace(alvo, "\\" + alvo)
        return linha

    corpo = "".join(f"({escapar(linha)}) Tj T*\n" for linha in linhas)
    fluxo = f"BT /F1 10 Tf 40 780 Td 12 TL\n{corpo}ET"

    filhos = " ".join(f"{3 + i} 0 R" for i in range(paginas))
    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{filhos}] /Count {paginas} >>",
    ]
    for _ in range(paginas):
        objetos.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {3 + paginas} 0 R >> >> "
            f"/Contents {4 + paginas} 0 R >>"
        )
    objetos.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objetos.append(f"<< /Length {len(fluxo)} >>\nstream\n{fluxo}\nendstream")

    saida, deslocamentos = "%PDF-1.4\n", []
    for numero, objeto in enumerate(objetos, 1):
        deslocamentos.append(len(saida))
        saida += f"{numero} 0 obj\n{objeto}\nendobj\n"

    inicio = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n"
    saida += "".join(f"{d:010d} 00000 n \n" for d in deslocamentos)
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        f"startxref\n{inicio}\n%%EOF"
    )
    return saida.encode("latin-1")


# --------------------------------------------------------------------------- #
# Mercado Pago: data, descrição, ID da operação, valor, saldo
# --------------------------------------------------------------------------- #
MERCADO_PAGO = pdf(
    [
        "1/2",
        "EXTRATO DE CONTA",
        "Kamilly da Rosa",
        "Saldo inicial: R$ 0,00",
        "DETALHE DOS MOVIMENTOS",
        "Data Descrição ID da operação Valor Saldo",
        "01-08-2026",
        "Pix recebido Guilherme ",
        "Henrique Pinheiro Goncalves 171656539814 R$ 100,00 R$ 100,00",
        "03-08-2026 Dinheiro retirado controle 171937846478 R$ 250,97 R$ 250,97",
        "03-08-2026 Dinheiro reservado fatura 171039088519 R$ -250,97 R$ 0,00",
        "Saldo final: R$ 100,00",
    ]
)


class TestMercadoPago:
    def test_le_as_transacoes(self):
        assert len(ler_pdf(MERCADO_PAGO)) == 3

    def test_o_saldo_da_linha_nao_vira_valor(self):
        """Cada linha traz dois valores: o da transação e o saldo corrente.

        Pegar o último importaria o saldo no lugar do lançamento — número
        plausível e errado, que é o pior tipo de defeito.
        """
        por_descricao = {t.descricao: t.valor for t in ler_pdf(MERCADO_PAGO)}
        assert por_descricao["Dinheiro retirado controle"] == Decimal("250.97")
        assert por_descricao["Dinheiro reservado fatura"] == Decimal("250.97")

    def test_descricao_quebrada_em_duas_linhas_e_remontada(self):
        descricoes = {t.descricao for t in ler_pdf(MERCADO_PAGO)}
        assert "Pix recebido Guilherme Henrique Pinheiro Goncalves" in descricoes

    def test_data_sozinha_numa_linha_vale_para_a_seguinte(self):
        primeira = ler_pdf(MERCADO_PAGO)[0]
        assert primeira.data == date(2026, 8, 1)

    def test_o_sinal_define_o_sentido(self):
        por_descricao = {t.descricao: t.saida for t in ler_pdf(MERCADO_PAGO)}
        assert por_descricao["Dinheiro retirado controle"] is False
        assert por_descricao["Dinheiro reservado fatura"] is True

    def test_usa_o_id_da_operacao_como_identificador(self):
        primeira = ler_pdf(MERCADO_PAGO)[0]
        assert primeira.fitid.startswith("171656539814")

    def test_pix_e_estorno_compartilham_o_id_e_nao_podem_colidir(self):
        """Achado no extrato real: o ID é da operação, não da transação.

        Um Pix e o estorno dele carregam o mesmo número. Sem o valor assinado
        junto, um dos dois sumiria como duplicata — no extrato de agosto eram
        três pares de R$ 89,00.
        """
        conteudo = pdf(
            [
                "EXTRATO DE CONTA",
                "Data Descrição ID da operação Valor Saldo",
                "05-08-2026 Pix enviado Jose 171322327941 R$ -89,00 R$ 0,00",
                "05-08-2026 Reembolso de Pix enviado Jose 171322327941 R$ 89,00 R$ 89,00",
            ]
        )
        transacoes = ler_pdf(conteudo)
        assert len(transacoes) == 2
        assert len({t.fitid for t in transacoes}) == 2

    def test_duas_transacoes_iguais_no_mesmo_dia_continuam_duas(self):
        """O outro lado: o sintético juntaria estas, o ID as separa.

        Também vem do extrato real — dois "Pix enviado Jose Vieira da Silva"
        de R$ 89,00 no mesmo dia, operações diferentes.
        """
        conteudo = pdf(
            [
                "EXTRATO DE CONTA",
                "Data Descrição ID da operação Valor Saldo",
                "05-08-2026 Pix enviado Jose 171322327941 R$ -89,00 R$ 0,00",
                "05-08-2026 Pix enviado Jose 172223727894 R$ -89,00 R$ 0,00",
            ]
        )
        assert len({t.fitid for t in ler_pdf(conteudo)}) == 2


# --------------------------------------------------------------------------- #
# Nubank: o sentido vem do cabeçalho do dia, não da linha
# --------------------------------------------------------------------------- #
NUBANK = pdf(
    [
        "Kamilly da Rosa ",
        "Movimentações",
        "08 AGO 2026 Total de entradas + 941,55",
        "Transferencia recebida pelo Pix Kamilly da Rosa - MERCADO PAGO ",
        "IP LTDA. (0323) Agência: 1 Conta: 4100275488-6",
        "941,55",
        "09 AGO 2026 Total de saídas - 941,52",
        "Pagamento de fatura 941,52",
        "11 AGO 2026 Total de entradas + 0,01",
        "Resgate RDB 0,01",
        "Tem alguma dúvida? Mande uma mensagem pelo chat do app.",
        "nubank.com.br/contatos#ouvidoria",
    ]
)


class TestNubank:
    def test_le_as_transacoes(self):
        assert len(ler_pdf(NUBANK)) == 3

    def test_o_sentido_vem_do_cabecalho_do_dia(self):
        """O valor da transação vem sem sinal; quem diz o sentido é o dia."""
        por_descricao = {t.descricao: t.saida for t in ler_pdf(NUBANK)}
        assert por_descricao["Pagamento de fatura"] is True
        assert por_descricao["Resgate RDB"] is False

    def test_data_com_mes_por_extenso(self):
        assert [t.data for t in ler_pdf(NUBANK)] == [
            date(2026, 8, 8),
            date(2026, 8, 9),
            date(2026, 8, 11),
        ]

    def test_descricao_quebrada_com_valor_em_linha_propria(self):
        primeira = ler_pdf(NUBANK)[0]
        assert primeira.descricao.startswith("Transferencia recebida pelo Pix")
        assert primeira.valor == Decimal("941.55")

    def test_numero_de_conta_nao_vira_valor(self):
        """`Conta: 4100275488-6` termina em número e não tem centavos.

        Exigir os centavos no padrão é o que impede o número da conta, o CNPJ
        e o CEP de virarem lançamentos.
        """
        assert len(ler_pdf(NUBANK)) == 3

    def test_rodape_nao_vira_lancamento(self):
        descricoes = " ".join(t.descricao for t in ler_pdf(NUBANK))
        assert "dúvida" not in descricoes


class TestQuandoNaoDaParaLer:
    def test_banco_desconhecido(self):
        conteudo = pdf(
            [
                "Banco Qualquer - Extrato",
                "08/08/2026  Compra no mercado  -30,00",
            ]
        )
        with pytest.raises(ErroPDF, match="não reconheço o layout|Não reconheço o layout"):
            ler_pdf(conteudo)

    def test_pdf_sem_texto_diz_que_e_escaneado(self):
        """O sintoma mais confuso: o arquivo abre, mas não tem texto nenhum."""
        with pytest.raises(ErroPDF, match="escaneado"):
            ler_pdf(pdf([]))

    def test_arquivo_que_nao_e_pdf(self):
        with pytest.raises(ErroPDF, match="abrir"):
            ler_pdf(b"isto nao e um pdf")

    def test_layout_conhecido_mas_sem_lancamento(self):
        conteudo = pdf(
            [
                "EXTRATO DE CONTA",
                "Data Descrição ID da operação Valor Saldo",
                "Nenhum movimento no período.",
            ]
        )
        with pytest.raises(ErroPDF, match="Mercado Pago"):
            ler_pdf(conteudo)

    def test_o_erro_e_um_erro_de_extrato(self):
        """O roteador captura `ErroExtrato`; sem a herança, viraria 500."""
        with pytest.raises(ErroExtrato):
            ler_pdf(b"isto nao e um pdf")


class TestIdentificador:
    def test_e_estavel_entre_leituras(self):
        assert [t.fitid for t in ler_pdf(MERCADO_PAGO)] == [
            t.fitid for t in ler_pdf(MERCADO_PAGO)
        ]

    def test_sem_id_do_banco_cai_no_sintetico(self):
        """O Nubank não põe identificador no PDF — lá vale o sintético."""
        primeira = ler_pdf(NUBANK)[0]
        assert primeira.fitid.startswith("2026-08-08|")
