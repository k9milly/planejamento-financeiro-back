"""`total_comprometido` do cartão: o que ainda vai ser cobrado (seção 24).

A fatura do mês responde "quanto devo até o fim deste mês". Esta é outra
pergunta: "quanto já está lançado e ainda vai ser cobrado", com as parcelas
futuras incluídas.

**O que torna o teste necessário:** a conta parece fácil de tirar do resumo
anual, e é justamente isso que não funciona — o resumo para em dezembro, e
uma compra em 12x feita em novembro tem dez parcelas no ano seguinte. Por
isso quase todo teste daqui atravessa a virada de ano de propósito.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

ANO = 2026


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


def fatura(cliente, cartao, mes, ano=ANO):
    resposta = cliente.get(f"/anos/{ano}/cartoes/{cartao['id']}/fatura/{mes}")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def parcelar(cliente, cartao, *, total, parcelas, data=f"{ANO}-11-15"):
    return cliente.post(
        f"/anos/{ANO}/compras-parceladas",
        json={
            "descricao": "Compra",
            "conta_id": cartao["id"],
            "data_primeira_parcela": data,
            "numero_parcelas": parcelas,
            "tem_juros": False,
            "valor_total": total,
        },
    )


class TestOExemploDaKamilly:
    """R$ 60 em 2x: R$ 30 neste mês, R$ 60 comprometidos."""

    def test_a_fatura_do_mes_mostra_so_a_primeira_parcela(self, cliente, ano, cartao):
        parcelar(cliente, cartao, total="60.00", parcelas=2)
        assert fatura(cliente, cartao, 11)["valor_em_aberto"] == "30.00"

    def test_o_total_comprometido_mostra_as_duas(self, cliente, ano, cartao):
        parcelar(cliente, cartao, total="60.00", parcelas=2)
        assert fatura(cliente, cartao, 11)["total_comprometido"] == "60.00"

    def test_depois_de_pagar_novembro_sobra_so_dezembro(self, cliente, ano, cartao):
        """O pagamento zera a fatura do mês e **não** zera o comprometido.

        É o caso que explica o campo: quem pagou novembro ainda deve
        dezembro, e a tela precisa dizer isso.
        """
        parcelar(cliente, cartao, total="60.00", parcelas=2)
        pago = cliente.post(f"/anos/{ANO}/cartoes/{cartao['id']}/fatura/11/pagar")
        assert pago.status_code == 201, pago.text

        depois = fatura(cliente, cartao, 11)
        assert depois["valor_em_aberto"] == "0.00"
        assert depois["total_comprometido"] == "30.00"


class TestAtravessandoOAno:
    """O motivo de a conta não poder sair do resumo anual."""

    def test_parcelas_do_ano_seguinte_entram(self, cliente, ano, cartao):
        """12x a partir de novembro: dez parcelas caem em 2027.

        O fechamento de dezembro de 2026 não enxerga nenhuma delas. Se este
        número viesse do resumo, diria R$ 20,00 — a dívida real é R$ 120,00.
        """
        parcelar(cliente, cartao, total="120.00", parcelas=12)

        novembro = fatura(cliente, cartao, 11)
        assert novembro["valor_em_aberto"] == "10.00"
        assert novembro["total_comprometido"] == "120.00"

    def test_dezembro_ainda_ve_o_que_vem_depois(self, cliente, ano, cartao):
        """Consultado em dezembro, o comprometido é só o que falta.

        Dezembro é o mês em que o resumo anual e a realidade se separam: a
        fatura de dezembro fecha o ano, e sobram dez parcelas em 2027.
        """
        parcelar(cliente, cartao, total="120.00", parcelas=12)

        dezembro = fatura(cliente, cartao, 12)
        assert dezembro["valor_em_aberto"] == "20.00"
        assert dezembro["total_comprometido"] == "120.00"


class TestOQueEntraEOQueNaoEntra:
    def test_compra_avulsa_futura_entra(self, cliente, ano, cartao):
        cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": f"{ANO}-12-20",
                "valor": "45.00",
                "tipo": "saida",
                "conta_id": cartao["id"],
                "forma_pagamento": "credito",
                "descricao": "Presente",
            },
        )
        assert fatura(cliente, cartao, 11)["total_comprometido"] == "45.00"

    def test_compra_passada_nao_e_contada_duas_vezes(self, cliente, ano, cartao):
        """Ela já está na fatura do mês; somá-la de novo dobraria a dívida."""
        cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": f"{ANO}-11-02",
                "valor": "45.00",
                "tipo": "saida",
                "conta_id": cartao["id"],
                "forma_pagamento": "credito",
                "descricao": "Mercado",
            },
        )
        novembro = fatura(cliente, cartao, 11)
        assert novembro["valor_em_aberto"] == "45.00"
        assert novembro["total_comprometido"] == "45.00"

    def test_gasto_de_outro_cartao_nao_entra(self, cliente, ano, cartao, corrente):
        outro = cliente.post(
            "/contas",
            json={
                "nome": "Cartao Nu",
                "tipo": "cartao_credito",
                "dia_vencimento_fatura": 5,
            },
        ).json()
        parcelar(cliente, outro, total="900.00", parcelas=3)

        assert fatura(cliente, cartao, 11)["total_comprometido"] == "0.00"

    def test_gasto_na_conta_corrente_nao_entra(self, cliente, ano, cartao, corrente):
        cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": f"{ANO}-12-20",
                "valor": "500.00",
                "tipo": "saida",
                "conta_id": corrente["id"],
                "forma_pagamento": "pix",
                "descricao": "Aluguel",
            },
        )
        assert fatura(cliente, cartao, 11)["total_comprometido"] == "0.00"

    def test_pagamento_de_fatura_futura_abate(self, cliente, ano, cartao, corrente):
        """Transferência para o cartão é pagamento, e diminui o que falta.

        Sem o abatimento, pagar uma fatura adiantado deixaria o comprometido
        inalterado — a pessoa veria uma dívida que ela acabou de quitar.

        **A fatura de um mês é cumulativa**, e isso surpreende: com novembro
        em aberto, a fatura de dezembro cobra as duas parcelas, não só a de
        dezembro. Pagar dezembro, portanto, quita o cartão inteiro, e o
        comprometido vai a zero. A primeira versão deste teste esperava
        R$ 30,00 por supor que cada mês cobrasse só o seu.
        """
        parcelar(cliente, cartao, total="60.00", parcelas=2)
        assert fatura(cliente, cartao, 11)["total_comprometido"] == "60.00"
        assert fatura(cliente, cartao, 12)["valor_em_aberto"] == "60.00"

        pago = cliente.post(f"/anos/{ANO}/cartoes/{cartao['id']}/fatura/12/pagar")
        assert pago.status_code == 201, pago.text

        assert fatura(cliente, cartao, 11)["total_comprometido"] == "0.00"

    def test_pagar_mes_a_mes_zera_aos_poucos(self, cliente, ano, cartao, corrente):
        """O caminho normal: paga novembro, sobra dezembro; paga dezembro, zera."""
        parcelar(cliente, cartao, total="60.00", parcelas=2)

        cliente.post(f"/anos/{ANO}/cartoes/{cartao['id']}/fatura/11/pagar")
        assert fatura(cliente, cartao, 11)["total_comprometido"] == "30.00"

        cliente.post(f"/anos/{ANO}/cartoes/{cartao['id']}/fatura/12/pagar")
        assert fatura(cliente, cartao, 11)["total_comprometido"] == "0.00"


class TestSemNada:
    def test_cartao_sem_lancamento_nenhum(self, cliente, ano, cartao):
        vazia = fatura(cliente, cartao, 11)
        assert vazia["valor_em_aberto"] == "0.00"
        assert vazia["total_comprometido"] == "0.00"

    def test_sem_parcela_futura_os_dois_numeros_sao_iguais(self, cliente, ano, cartao):
        """É o caso em que a tela esconde a linha — e é a maioria dos meses."""
        cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": f"{ANO}-11-02",
                "valor": "45.00",
                "tipo": "saida",
                "conta_id": cartao["id"],
                "forma_pagamento": "credito",
                "descricao": "Mercado",
            },
        )
        novembro = fatura(cliente, cartao, 11)
        assert novembro["total_comprometido"] == novembro["valor_em_aberto"]


class TestValorNegativoNaoEMascarado:
    def test_credito_no_cartao_aparece_como_negativo(
        self, cliente, ano, cartao, corrente
    ):
        """Pagar mais do que se deve dá crédito, e o número diz isso.

        Forçar zero aqui faria `valor_em_aberto` e `total_comprometido`
        discordarem sobre o mesmo fato, na mesma tela.
        """
        cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": f"{ANO}-12-05",
                "valor": "200.00",
                "tipo": "transferencia",
                "conta_id": corrente["id"],
                "conta_destino_id": cartao["id"],
                "descricao": "Adiantamento",
            },
        )
        assert Decimal(fatura(cliente, cartao, 11)["total_comprometido"]) < 0
