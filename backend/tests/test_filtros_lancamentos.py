"""Filtros novos do `GET /anos/{ano}/lancamentos` (seção 23).

Quatro filtros: forma de pagamento, parcelado, valor mínimo e máximo. Todos
se combinam com "e", e todos são feitos no servidor — a busca por texto é que
continua no cliente.

**O filtro que exige atenção é `nao_informado`.** Entrada, transferência e
guardado também têm `forma_pagamento` nulo, então ele só significa "saída por
classificar" se a consulta restringir a saídas primeiro. Sem isso o filtro
traria o extrato inteiro, e pareceria funcionar.
"""

from __future__ import annotations

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


def lancar(cliente, conta, **extras):
    corpo = {
        "data": f"{ANO}-03-10",
        "valor": "100.00",
        "tipo": "saida",
        "conta_id": conta["id"],
        "descricao": "Compra",
    }
    corpo.update(extras)
    resposta = cliente.post(f"/anos/{ANO}/lancamentos", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def listar(cliente, **filtros):
    resposta = cliente.get(f"/anos/{ANO}/lancamentos", params=filtros)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def descricoes(linhas):
    return sorted(linha["descricao"] for linha in linhas)


@pytest.fixture()
def variedade(cliente, ano, corrente, cartao):
    """Um de cada, para os filtros terem o que separar."""
    lancar(cliente, corrente, forma_pagamento="pix", descricao="Pix")
    lancar(cliente, corrente, forma_pagamento="debito", descricao="Debito")
    lancar(cliente, corrente, forma_pagamento="dinheiro", descricao="Dinheiro")
    lancar(cliente, cartao, forma_pagamento="credito", descricao="Credito")
    # Sem forma: é o que chega de extrato importado.
    lancar(cliente, corrente, descricao="Sem forma")
    # Os três que também têm forma_pagamento nulo, e **não** são saída.
    lancar(cliente, corrente, tipo="entrada", descricao="Salario")
    lancar(
        cliente,
        corrente,
        tipo="transferencia",
        conta_destino_id=cartao["id"],
        descricao="Pagamento",
    )
    lancar(cliente, corrente, tipo="guardado", descricao="Reserva")


class TestFormaDePagamento:
    def test_cada_forma_traz_so_a_sua(self, cliente, variedade):
        for forma, esperado in [
            ("pix", "Pix"),
            ("debito", "Debito"),
            ("dinheiro", "Dinheiro"),
            ("credito", "Credito"),
        ]:
            assert descricoes(listar(cliente, forma_pagamento=forma)) == [esperado]

    def test_nao_informado_traz_so_a_saida_sem_forma(self, cliente, variedade):
        """O teste que importa: entrada, transferência e guardado ficam fora.

        Os três têm `forma_pagamento` nulo. Sem restringir a saídas antes, o
        filtro traria os quatro e ninguém notaria de cara — a lista viria
        cheia, só que errada.
        """
        assert descricoes(listar(cliente, forma_pagamento="nao_informado")) == [
            "Sem forma"
        ]

    def test_nao_informado_e_debito_sao_coisas_diferentes(self, cliente, variedade):
        """Decisão da Kamilly, contra o que o cálculo de saldo faz.

        O ADR-0001 trata nulo como débito ao somar. Aqui não: o filtro serve
        para achar o que falta classificar, e juntar os dois esconderia
        exatamente isso.
        """
        assert descricoes(listar(cliente, forma_pagamento="debito")) == ["Debito"]
        assert descricoes(listar(cliente, forma_pagamento="nao_informado")) == [
            "Sem forma"
        ]

    def test_com_tipo_que_nao_e_saida_recusa(self, cliente, variedade):
        resposta = cliente.get(
            f"/anos/{ANO}/lancamentos",
            params={"forma_pagamento": "pix", "tipo": "entrada"},
        )
        assert resposta.status_code == 422
        assert "saídas" in resposta.json()["detail"]

    def test_com_tipo_saida_explicito_funciona(self, cliente, variedade):
        assert descricoes(
            listar(cliente, forma_pagamento="pix", tipo="saida")
        ) == ["Pix"]

    def test_valor_invalido_e_recusado_pelo_proprio_contrato(self, cliente, variedade):
        resposta = cliente.get(
            f"/anos/{ANO}/lancamentos", params={"forma_pagamento": "boleto"}
        )
        assert resposta.status_code == 422


class TestParcelado:
    @pytest.fixture()
    def com_parcelas(self, cliente, ano, cartao, corrente):
        cliente.post(
            f"/anos/{ANO}/compras-parceladas",
            json={
                "descricao": "Tenis",
                "conta_id": cartao["id"],
                "data_primeira_parcela": f"{ANO}-03-10",
                "numero_parcelas": 3,
                "tem_juros": False,
                "valor_total": "300.00",
            },
        )
        lancar(cliente, corrente, forma_pagamento="pix", descricao="Avulsa")

    def test_so_parceladas(self, cliente, com_parcelas):
        linhas = listar(cliente, parcelado=True)
        assert len(linhas) == 3
        assert all(linha["descricao"].startswith("Tenis") for linha in linhas)

    def test_o_contrario_traz_o_resto(self, cliente, com_parcelas):
        assert descricoes(listar(cliente, parcelado=False)) == ["Avulsa"]

    def test_sem_o_filtro_vem_tudo(self, cliente, com_parcelas):
        assert len(listar(cliente)) == 4

    def test_pega_tambem_a_parcela_sem_grupo(
        self, cliente, ano, cartao, sessao_teste
    ):
        """A fatura importada preenche `numero_parcela` e não cria grupo.

        São duas origens de parcela (ADR-14 e ADR-19). Olhar só
        `compra_parcelada_id` deixaria as importadas de fora — e este teste
        existe desde já porque a 15c ainda não gravou nenhuma dessas.
        """
        from app.models import Lancamento

        criado = lancar(
            cliente, cartao, forma_pagamento="credito", descricao="Importada"
        )
        db = sessao_teste()
        try:
            lanc = db.get(Lancamento, int(criado["id"]))
            lanc.numero_parcela = 2
            db.commit()
        finally:
            db.close()

        assert descricoes(listar(cliente, parcelado=True)) == ["Importada"]


class TestFaixaDeValor:
    @pytest.fixture()
    def escada(self, cliente, ano, corrente):
        for valor in ("10.00", "50.00", "100.00", "500.00"):
            lancar(cliente, corrente, valor=valor, descricao=f"R$ {valor}")

    def test_minimo_e_inclusivo(self, cliente, escada):
        assert descricoes(listar(cliente, valor_min="50.00")) == [
            "R$ 100.00",
            "R$ 50.00",
            "R$ 500.00",
        ]

    def test_maximo_e_inclusivo(self, cliente, escada):
        assert descricoes(listar(cliente, valor_max="50.00")) == [
            "R$ 10.00",
            "R$ 50.00",
        ]

    def test_faixa_fechada(self, cliente, escada):
        assert descricoes(listar(cliente, valor_min="50.00", valor_max="100.00")) == [
            "R$ 100.00",
            "R$ 50.00",
        ]

    def test_minimo_maior_que_maximo_recusa(self, cliente, escada):
        resposta = cliente.get(
            f"/anos/{ANO}/lancamentos",
            params={"valor_min": "100.00", "valor_max": "50.00"},
        )
        assert resposta.status_code == 422
        assert "máximo" in resposta.json()["detail"]

    def test_compara_com_o_valor_sempre_positivo(self, cliente, ano, corrente):
        """O sinal vem do tipo, não do número — uma saída de R$ 100 é 100.

        Se a comparação fosse com um valor assinado, `valor_min=50` perderia
        toda saída, que é justamente o que a pessoa está filtrando.
        """
        lancar(cliente, corrente, valor="100.00", tipo="saida", descricao="Saida")
        lancar(cliente, corrente, valor="100.00", tipo="entrada", descricao="Entrada")
        assert descricoes(listar(cliente, valor_min="100.00")) == [
            "Entrada",
            "Saida",
        ]


class TestCombinados:
    def test_os_filtros_se_somam(self, cliente, ano, corrente, cartao):
        lancar(cliente, corrente, valor="10.00", forma_pagamento="pix", descricao="A")
        lancar(cliente, corrente, valor="900.00", forma_pagamento="pix", descricao="B")
        lancar(
            cliente, corrente, valor="900.00", forma_pagamento="debito", descricao="C"
        )

        assert descricoes(
            listar(cliente, forma_pagamento="pix", valor_min="100.00")
        ) == ["B"]

    def test_combinam_com_os_filtros_que_ja_existiam(self, cliente, ano, corrente):
        lancar(
            cliente,
            corrente,
            data=f"{ANO}-03-10",
            forma_pagamento="pix",
            descricao="Marco",
        )
        lancar(
            cliente,
            corrente,
            data=f"{ANO}-04-10",
            forma_pagamento="pix",
            descricao="Abril",
        )
        assert descricoes(listar(cliente, forma_pagamento="pix", mes=4)) == ["Abril"]
