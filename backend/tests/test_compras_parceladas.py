"""Compra parcelada no cartão de crédito (ADR-14).

A regra que amarra tudo: cada parcela é um `Lancamento` comum, gerado na hora
da compra. Por isso quase todo teste aqui olha para os lançamentos gerados, e
não para a tabela nova — é onde o dinheiro de fato aparece.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.tempo import hoje

ANO = hoje().year


@pytest.fixture()
def ano(cliente):
    cliente.post("/anos", json={"ano": ANO})
    return ANO


@pytest.fixture()
def cartao(cliente):
    return cliente.post(
        "/contas",
        json={"nome": "Cartão MP", "tipo": "cartao_credito", "dia_vencimento_fatura": 13},
    ).json()


def comprar(cliente, cartao, **extras):
    corpo = {
        "descricao": "Tenis",
        "conta_id": cartao["id"],
        "data_primeira_parcela": f"{ANO}-03-10",
        "numero_parcelas": 3,
        "tem_juros": False,
        "valor_total": "100.00",
    }
    corpo.update(extras)
    return cliente.post(f"/anos/{ANO}/compras-parceladas", json=corpo)


def lancamentos(cliente, ano=ANO):
    return cliente.get(f"/anos/{ano}/lancamentos").json()


class TestSemJuros:
    def test_divide_o_total_e_a_ultima_absorve_o_resto(self, cliente, ano, cartao):
        """R$ 100 em 3x são 33,33 + 33,33 + 33,34 — a sobra não some."""
        compra = comprar(cliente, cartao).json()

        valores = [p["valor"] for p in compra["parcelas"]]
        assert valores == ["33.33", "33.33", "33.34"]
        assert sum(Decimal(v) for v in valores) == Decimal("100.00")

    def test_o_grupo_guarda_o_valor_comum_e_o_total(self, cliente, ano, cartao):
        compra = comprar(cliente, cartao).json()
        assert compra["valor_parcela"] == "33.33"
        assert compra["valor_total"] == "100.00"

    def test_divisao_exata_nao_inventa_centavo(self, cliente, ano, cartao):
        compra = comprar(cliente, cartao, valor_total="90.00").json()
        assert [p["valor"] for p in compra["parcelas"]] == ["30.00", "30.00", "30.00"]


class TestJurosPorValorDaParcela:
    """O modo exato: a pessoa digita o que o cartão já mostra."""

    def test_so_multiplica(self, cliente, ano, cartao):
        compra = comprar(
            cliente,
            cartao,
            tem_juros=True,
            modo_juros="valor",
            valor_total=None,
            valor_parcela="105.32",
            numero_parcelas=10,
        ).json()

        assert compra["valor_parcela"] == "105.32"
        assert compra["valor_total"] == "1053.20"
        assert {p["valor"] for p in compra["parcelas"]} == {"105.32"}

    def test_todas_as_parcelas_saem_iguais(self, cliente, ano, cartao):
        """Sem divisão, não há resto para a última absorver."""
        compra = comprar(
            cliente, cartao, tem_juros=True, modo_juros="valor",
            valor_total=None, valor_parcela="33.33",
        ).json()
        assert [p["valor"] for p in compra["parcelas"]] == ["33.33"] * 3


class TestJurosPorTaxa:
    def test_juros_simples_conforme_o_adr(self, cliente, ano, cartao):
        """R$ 1.000 em 10x a 2% ao mês: juros = 1000 × 0,02 × 10 = R$ 200."""
        compra = comprar(
            cliente, cartao, tem_juros=True, modo_juros="percentual",
            valor_total="1000.00", taxa_juros_pct="2.00", numero_parcelas=10,
        ).json()

        assert compra["valor_total"] == "1200.00"
        assert compra["valor_parcela"] == "120.00"

    def test_o_total_guardado_e_com_juros_nao_o_preco_a_vista(
        self, cliente, ano, cartao
    ):
        """O campo entra como preço à vista e sai como soma das parcelas."""
        compra = comprar(
            cliente, cartao, tem_juros=True, modo_juros="percentual",
            valor_total="100.00", taxa_juros_pct="1.00", numero_parcelas=2,
        ).json()

        assert compra["valor_total"] == "102.00"
        assert sum(Decimal(p["valor"]) for p in compra["parcelas"]) == Decimal("102.00")

    def test_arredondamento_tambem_cai_na_ultima(self, cliente, ano, cartao):
        compra = comprar(
            cliente, cartao, tem_juros=True, modo_juros="percentual",
            valor_total="100.00", taxa_juros_pct="1.00", numero_parcelas=3,
        ).json()

        valores = [Decimal(p["valor"]) for p in compra["parcelas"]]
        assert sum(valores) == Decimal(compra["valor_total"])
        assert valores[-1] >= valores[0]

    def test_taxa_alta_nao_quebra(self, cliente, ano, cartao):
        compra = comprar(
            cliente, cartao, tem_juros=True, modo_juros="percentual",
            valor_total="500.00", taxa_juros_pct="17.90", numero_parcelas=12,
        ).json()
        assert Decimal(compra["valor_total"]) > Decimal("500.00")


class TestCombinacoesInvalidas:
    """Aceitar um campo que não pertence ao modo seria pior que recusar: o
    valor digitado seria ignorado em silêncio."""

    def test_sem_juros_exige_o_total(self, cliente, ano, cartao):
        assert comprar(cliente, cartao, valor_total=None).status_code == 422

    def test_com_juros_exige_o_modo(self, cliente, ano, cartao):
        resposta = comprar(cliente, cartao, tem_juros=True)
        assert resposta.status_code == 422

    def test_modo_valor_exige_o_valor_da_parcela(self, cliente, ano, cartao):
        resposta = comprar(
            cliente, cartao, tem_juros=True, modo_juros="valor", valor_total=None
        )
        assert resposta.status_code == 422

    def test_modo_percentual_exige_taxa(self, cliente, ano, cartao):
        resposta = comprar(
            cliente, cartao, tem_juros=True, modo_juros="percentual"
        )
        assert resposta.status_code == 422

    def test_sem_juros_recusa_taxa(self, cliente, ano, cartao):
        resposta = comprar(cliente, cartao, taxa_juros_pct="2.00")
        assert resposta.status_code == 422

    def test_modo_valor_recusa_total(self, cliente, ano, cartao):
        resposta = comprar(
            cliente, cartao, tem_juros=True, modo_juros="valor",
            valor_parcela="10.00", valor_total="100.00",
        )
        assert resposta.status_code == 422

    def test_uma_parcela_so_nao_e_parcelamento(self, cliente, ano, cartao):
        assert comprar(cliente, cartao, numero_parcelas=1).status_code == 422

    def test_teto_de_vinte_e_quatro(self, cliente, ano, cartao):
        """Sem teto, um '240' digitado por engano geraria 240 lançamentos."""
        assert comprar(cliente, cartao, numero_parcelas=25).status_code == 422
        assert comprar(cliente, cartao, numero_parcelas=24).status_code == 201


class TestConta:
    def test_so_em_cartao_de_credito(self, cliente, ano, conta):
        resposta = comprar(cliente, conta)
        assert resposta.status_code == 422
        assert "cartão de crédito" in resposta.json()["detail"]

    def test_conta_inexistente(self, cliente, ano, cartao):
        assert comprar(cliente, {"id": 9999}).status_code == 422


class TestAsParcelasGeradas:
    def test_uma_por_mes_a_partir_da_primeira(self, cliente, ano, cartao):
        compra = comprar(cliente, cartao).json()
        assert [p["data"] for p in compra["parcelas"]] == [
            f"{ANO}-03-10",
            f"{ANO}-04-10",
            f"{ANO}-05-10",
        ]

    def test_dia_que_nao_existe_no_mes_cai_no_ultimo(self, cliente, ano, cartao):
        """Dia 31 em abril vira 30 — mesmo tratamento dos gastos fixos."""
        compra = comprar(
            cliente, cartao, data_primeira_parcela=f"{ANO}-03-31", numero_parcelas=2
        ).json()
        assert [p["data"] for p in compra["parcelas"]] == [
            f"{ANO}-03-31",
            f"{ANO}-04-30",
        ]

    def test_descricao_numerada(self, cliente, ano, cartao):
        compra = comprar(cliente, cartao).json()
        assert [p["descricao"] for p in compra["parcelas"]] == [
            "Tenis (1/3)",
            "Tenis (2/3)",
            "Tenis (3/3)",
        ]

    def test_sao_saidas_no_credito_do_cartao(self, cliente, ano, cartao):
        compra = comprar(cliente, cartao).json()
        for parcela in compra["parcelas"]:
            assert parcela["tipo"] == "saida"
            assert parcela["forma_pagamento"] == "credito"
            assert parcela["conta_id"] == cartao["id"]

    def test_carregam_o_numero_da_parcela(self, cliente, ano, cartao):
        compra = comprar(cliente, cartao).json()
        assert [p["numero_parcela"] for p in compra["parcelas"]] == [1, 2, 3]
        assert all(p["compra_parcelada_id"] == compra["id"] for p in compra["parcelas"])

    def test_aparecem_na_listagem_de_lancamentos(self, cliente, ano, cartao):
        comprar(cliente, cartao)
        assert len(lancamentos(cliente)) == 3

    def test_lancamento_comum_continua_sem_os_campos(self, cliente, ano, conta):
        cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": f"{ANO}-03-10",
                "valor": "10.00",
                "tipo": "saida",
                "conta_id": conta["id"],
            },
        )
        comum = lancamentos(cliente)[0]
        assert comum["compra_parcelada_id"] is None
        assert comum["numero_parcela"] is None

    def test_a_categoria_vai_para_todas(self, cliente, ano, cartao):
        categoria = cliente.post("/categorias", json={"nome": "Roupas"}).json()
        compra = comprar(cliente, cartao, categoria_id=categoria["id"]).json()
        assert all(p["categoria_id"] == categoria["id"] for p in compra["parcelas"])


class TestAnosFuturos:
    def test_cria_sozinho_o_ano_que_falta(self, cliente, ano, cartao):
        """A parcela é dívida já assumida — não pode ficar esperando alguém
        lembrar de criar o ano seguinte."""
        assert cliente.get("/anos").json() == [
            a for a in cliente.get("/anos").json() if a["ano"] == ANO
        ]

        compra = comprar(
            cliente, cartao, data_primeira_parcela=f"{ANO}-11-10", numero_parcelas=4
        ).json()

        anos = {a["ano"] for a in cliente.get("/anos").json()}
        assert ANO + 1 in anos
        assert [p["data"][:7] for p in compra["parcelas"]] == [
            f"{ANO}-11",
            f"{ANO}-12",
            f"{ANO + 1}-01",
            f"{ANO + 1}-02",
        ]

    def test_as_parcelas_ficam_no_ano_certo(self, cliente, ano, cartao):
        comprar(cliente, cartao, data_primeira_parcela=f"{ANO}-12-10", numero_parcelas=2)

        assert len(lancamentos(cliente, ANO)) == 1
        assert len(lancamentos(cliente, ANO + 1)) == 1

    def test_ano_de_destino_arquivado_recusa_a_compra_inteira(
        self, cliente, ano, cartao
    ):
        """Não desarquiva sozinho — e não grava metade das parcelas."""
        cliente.post("/anos", json={"ano": ANO + 1})
        cliente.post(f"/anos/{ANO + 1}/arquivar")

        resposta = comprar(
            cliente, cartao, data_primeira_parcela=f"{ANO}-12-10", numero_parcelas=2
        )
        assert resposta.status_code == 422
        assert str(ANO + 1) in resposta.json()["detail"]
        assert lancamentos(cliente, ANO) == []

    def test_primeira_parcela_precisa_ser_do_ano_da_rota(self, cliente, ano, cartao):
        resposta = comprar(cliente, cartao, data_primeira_parcela=f"{ANO + 1}-03-10")
        assert resposta.status_code == 422


class TestDesfazerACompra:
    def test_apagar_o_grupo_leva_as_parcelas(self, cliente, ano, cartao):
        compra = comprar(cliente, cartao).json()
        assert len(lancamentos(cliente)) == 3

        assert cliente.delete(
            f"/anos/{ANO}/compras-parceladas/{compra['id']}"
        ).status_code == 204
        assert lancamentos(cliente) == []

    def test_apaga_parcelas_de_outros_anos_tambem(self, cliente, ano, cartao):
        compra = comprar(
            cliente, cartao, data_primeira_parcela=f"{ANO}-12-10", numero_parcelas=2
        ).json()

        cliente.delete(f"/anos/{ANO}/compras-parceladas/{compra['id']}")
        assert lancamentos(cliente, ANO) == []
        assert lancamentos(cliente, ANO + 1) == []

    def test_grupo_inexistente(self, cliente, ano, cartao):
        assert cliente.delete(f"/anos/{ANO}/compras-parceladas/9999").status_code == 404

    def test_apagar_uma_parcela_isolada_nao_mexe_nas_outras(
        self, cliente, ano, cartao
    ):
        """A parcela é um lançamento como outro qualquer — sem regra nova."""
        compra = comprar(cliente, cartao).json()
        primeira = compra["parcelas"][0]

        assert cliente.delete(
            f"/anos/{ANO}/lancamentos/{primeira['id']}"
        ).status_code == 204
        assert len(lancamentos(cliente)) == 2

    def test_editar_uma_parcela_nao_recalcula_as_outras(self, cliente, ano, cartao):
        """Correção pontual do mês, não renegociação da compra inteira."""
        compra = comprar(cliente, cartao).json()
        primeira = compra["parcelas"][0]

        cliente.patch(
            f"/anos/{ANO}/lancamentos/{primeira['id']}", json={"valor": "50.00"}
        )

        valores = sorted(l["valor"] for l in lancamentos(cliente))
        assert valores == ["33.33", "33.34", "50.00"]


class TestEfeitoNaFatura:
    def test_a_parcela_do_mes_entra_na_fatura_daquele_mes(self, cliente, ano, cartao):
        """Nada mudou em `calculos.py` — a parcela é um lançamento datado."""
        comprar(cliente, cartao)

        resumo = cliente.get(f"/anos/{ANO}/resumo").json()
        por_mes = {
            m["mes"]: next(
                (c["saldo"] for c in m["por_cartao"] if c["conta_id"] == cartao["id"]),
                None,
            )
            for m in resumo["meses"]
        }
        # Março fecha devendo a primeira parcela; abril, as duas primeiras.
        assert por_mes[3] == "-33.33"
        assert por_mes[4] == "-66.66"

    def test_parcela_futura_nao_entra_no_mes_de_hoje(self, cliente, ano, cartao):
        comprar(cliente, cartao)
        resumo = cliente.get(f"/anos/{ANO}/resumo").json()
        fevereiro = next(m for m in resumo["meses"] if m["mes"] == 2)
        assert fevereiro["por_cartao"] == [] or all(
            c["saldo"] == "0.00" for c in fevereiro["por_cartao"]
        )
