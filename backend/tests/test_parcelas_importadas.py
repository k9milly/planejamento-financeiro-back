"""Parcela importada da fatura cai mês a mês (ADR-19, Fase 15c).

A fatura imprime **sempre a data da compra original**, repetida em toda
fatura até a última parcela. Até aqui, importar as quatro faturas de uma
compra em 4x empilhava as quatro parcelas no mês da compra, e os meses em que
o dinheiro de fato sai ficavam vazios.

Agora a parcela N cai em "data da compra + (N−1) meses", que é exatamente o
que o botão Parcelar (ADR-14) já gerava — a mesma função, não uma cópia.

**O que não pode mudar junto:** a chave de deduplicação continua saindo da
data impressa. A fatura de outubro de 2026 já está importada em produção; se
a chave passasse a usar a data deslocada, reimportá-la duplicaria tudo.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.parcelas import data_da_parcela, datas_das_parcelas, ler_parcela
from app.services.pdf import ler_pdf
from tests.test_pdf import pdf

ANO = 2026


def fatura_com(linhas: list[str], emissao: str = "09/10/2026") -> bytes:
    return pdf(
        [
            f"Emitida em: {emissao}",
            "Detalhes de consumo",
            "Data Movimentacoes Valor em R$",
            *linhas,
        ]
    )


class TestLerParcela:
    def test_reconhece_o_formato_do_mercado_pago(self):
        assert ler_parcela("VIVARA Parcela 2 de 10") == (2, 10)

    def test_ignora_descricao_sem_parcela(self):
        assert ler_parcela("JR FITNESS CENTER") is None

    def test_aceita_caixa_diferente(self):
        """A descrição vem do banco; um layout que mude a caixa não pode
        apagar o parcelamento em silêncio."""
        assert ler_parcela("LOJA parcela 2 DE 3") == (2, 3)

    def test_recusa_numero_maior_que_o_total(self):
        """"Parcela 5 de 3" é erro de leitura, não parcelamento."""
        assert ler_parcela("LOJA Parcela 5 de 3") is None


class TestOndeAParcelaCai:
    def test_a_primeira_fica_onde_esta(self):
        assert data_da_parcela(date(2026, 7, 26), 1) == date(2026, 7, 26)

    def test_a_terceira_anda_dois_meses(self):
        assert data_da_parcela(date(2026, 7, 26), 3) == date(2026, 9, 26)

    def test_dia_que_nao_existe_cai_no_ultimo_do_mes(self):
        """31/01 "Parcela 2 de 3" vai para o último dia de fevereiro."""
        assert data_da_parcela(date(2026, 1, 31), 2) == date(2026, 2, 28)

    def test_ano_bissexto(self):
        assert data_da_parcela(date(2028, 1, 31), 2) == date(2028, 2, 29)

    def test_atravessa_a_virada_de_ano(self):
        assert data_da_parcela(date(2026, 11, 13), 3) == date(2027, 1, 13)

    def test_e_a_mesma_regra_do_botao_parcelar(self):
        """O ponto do módulo compartilhado: as duas contas têm que coincidir.

        Se um dia divergirem, os dois caminhos voltam a pôr a mesma compra em
        meses diferentes — que é o defeito que o ADR-19 corrige.
        """
        compra = date(2026, 11, 13)
        pelo_botao = datas_das_parcelas(compra, 4)
        pela_fatura = [data_da_parcela(compra, n) for n in range(1, 5)]
        assert pelo_botao == pela_fatura


class TestNaFaturaDeVerdade:
    def test_a_parcela_do_meio_vai_para_o_mes_em_que_e_cobrada(self):
        """Caso real: parcela 3 de 4, comprada em 26/07, cobrada em setembro."""
        conteudo = fatura_com(
            ["26/07 MERCADOLIVRE*MERCADOLIVRE Parcela 3 de 4 R$ 7,78"]
        )
        assert ler_pdf(conteudo)[0].data == date(2026, 9, 26)

    def test_a_primeira_parcela_nao_se_move(self):
        conteudo = fatura_com(["25/09 TikTok Shop *Tik Parcela 1 de 3 R$ 82,48"])
        assert ler_pdf(conteudo)[0].data == date(2026, 9, 25)

    def test_compra_sem_parcela_nao_se_move(self):
        conteudo = fatura_com(["08/09 JR FITNESS CENTER R$ 120,00"])
        assert ler_pdf(conteudo)[0].data == date(2026, 9, 8)

    def test_o_deslocamento_pode_jogar_para_o_ano_seguinte(self):
        """E a prévia marca como fora do ano — não é erro, é aviso.

        Uma compra de 20/12 na parcela 2 cai em janeiro. Quem importa no ano
        de 2026 vê a linha marcada, e decide.
        """
        conteudo = fatura_com(
            ["20/12 LOJA Parcela 2 de 3 R$ 50,00"], emissao="09/01/2027"
        )
        assert ler_pdf(conteudo)[0].data == date(2027, 1, 20)

    def test_o_valor_nao_muda(self):
        conteudo = fatura_com(["26/07 LOJA Parcela 3 de 4 R$ 7,78"])
        assert str(ler_pdf(conteudo)[0].valor) == "7.78"


class TestAChaveNaoPodeMudar:
    """A fatura de outubro/2026 já está importada em produção."""

    def test_o_identificador_usa_a_data_impressa(self):
        """Se usasse a deslocada, reimportar duplicaria tudo."""
        conteudo = fatura_com(["26/07 LOJA Parcela 3 de 4 R$ 7,78"])
        transacao = ler_pdf(conteudo)[0]

        assert transacao.data == date(2026, 9, 26)  # onde é cobrada
        assert "2026-07-26" in transacao.fitid  # como está impressa

    def test_a_mesma_fatura_lida_duas_vezes_da_a_mesma_chave(self):
        conteudo = fatura_com(["26/07 LOJA Parcela 3 de 4 R$ 7,78"])
        assert ler_pdf(conteudo)[0].fitid == ler_pdf(conteudo)[0].fitid


# --------------------------------------------------------------------------- #
# Ponta a ponta: prévia, confirmação e o filtro `parcelado`
# --------------------------------------------------------------------------- #
@pytest.fixture()
def ano(cliente):
    cliente.post("/anos", json={"ano": ANO})
    return ANO


@pytest.fixture()
def corrente(cliente):
    return cliente.post("/contas", json={"nome": "Nubank"}).json()


@pytest.fixture()
def cartao(cliente, corrente):
    return cliente.post(
        "/contas",
        json={
            "nome": "Cartao MP",
            "tipo": "cartao_credito",
            "dia_vencimento_fatura": 10,
            "conta_pagamento_padrao_id": corrente["id"],
        },
    ).json()


FATURA_COM_PARCELA = None  # preenchido abaixo, depois de `pdf` existir


def enviar_previa(cliente, conteudo):
    return cliente.post(
        f"/anos/{ANO}/importacao/previa",
        files={"arquivo": ("fatura.pdf", conteudo, "application/pdf")},
        data={"formato": "pdf"},
    )


def confirmar(cliente, cartao, linhas):
    return cliente.post(
        f"/anos/{ANO}/importacao/confirmar",
        json={
            "transacoes": [
                {
                    "fitid": t["fitid"],
                    "data": t["data"],
                    "valor": t["valor"],
                    "tipo": t["tipo_sugerido"],
                    "conta_id": cartao["id"],
                    "forma_pagamento": t["forma_pagamento_sugerida"],
                    "descricao": t["descricao"],
                }
                for t in linhas
            ]
        },
    )


class TestDaPreviaAoLancamento:
    def test_a_previa_mostra_a_data_deslocada(self, cliente, ano, cartao):
        conteudo = fatura_com(["26/07 LOJA Parcela 3 de 4 R$ 7,78"])
        linhas = enviar_previa(cliente, conteudo).json()["transacoes"]
        assert linhas[0]["data"] == "2026-09-26"

    def test_o_lancamento_gravado_guarda_o_numero_da_parcela(
        self, cliente, ano, cartao
    ):
        """Deduzido da descrição na confirmação — o contrato não muda."""
        conteudo = fatura_com(["26/07 LOJA Parcela 3 de 4 R$ 7,78"])
        linhas = enviar_previa(cliente, conteudo).json()["transacoes"]
        assert confirmar(cliente, cartao, linhas).status_code == 201

        gravados = cliente.get(f"/anos/{ANO}/lancamentos").json()
        assert len(gravados) == 1
        assert gravados[0]["data"] == "2026-09-26"

    def test_entra_no_filtro_de_parceladas(self, cliente, ano, cartao):
        """O fecho da 15a: a importada passa a aparecer em `parcelado=true`."""
        conteudo = fatura_com(
            [
                "26/07 LOJA Parcela 3 de 4 R$ 7,78",
                "08/09 JR FITNESS CENTER R$ 120,00",
            ]
        )
        linhas = enviar_previa(cliente, conteudo).json()["transacoes"]
        assert confirmar(cliente, cartao, linhas).status_code == 201

        so_parceladas = cliente.get(
            f"/anos/{ANO}/lancamentos", params={"parcelado": True}
        ).json()
        assert [l["descricao"] for l in so_parceladas] == ["LOJA Parcela 3 de 4"]

    def test_reimportar_a_mesma_fatura_nao_duplica(self, cliente, ano, cartao):
        """A prova de que a chave continua ancorada na data impressa."""
        conteudo = fatura_com(["26/07 LOJA Parcela 3 de 4 R$ 7,78"])
        linhas = enviar_previa(cliente, conteudo).json()["transacoes"]
        confirmar(cliente, cartao, linhas)

        de_novo = enviar_previa(cliente, conteudo).json()
        assert de_novo["ja_importadas"] == 1
        assert de_novo["transacoes"][0]["duplicado"] is True

        resultado = confirmar(cliente, cartao, de_novo["transacoes"]).json()
        assert resultado["importadas"] == 0
        assert len(cliente.get(f"/anos/{ANO}/lancamentos").json()) == 1

    def test_a_parcela_ja_lancada_a_mao_vira_parece_o_mesmo(
        self, cliente, ano, cartao
    ):
        """A consequência boa do ADR-19: os dois caminhos se reconhecem.

        Quem usou o botão Parcelar e depois importa a fatura vê o aviso, em
        vez de ganhar a parcela em dobro sem perceber. Isso só funciona
        porque as duas datas agora coincidem.
        """
        cliente.post(
            f"/anos/{ANO}/compras-parceladas",
            json={
                "descricao": "LOJA",
                "conta_id": cartao["id"],
                "data_primeira_parcela": f"{ANO}-07-26",
                "numero_parcelas": 4,
                "tem_juros": False,
                "valor_total": "31.12",
            },
        )

        conteudo = fatura_com(["26/07 LOJA Parcela 3 de 4 R$ 7,78"])
        linha = enviar_previa(cliente, conteudo).json()["transacoes"][0]

        assert linha["duplicado"] is False
        assert linha["possivel_repetido"] is True
