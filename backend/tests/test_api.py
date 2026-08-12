"""Testes de integração da API, contra um banco SQLite temporário."""

from __future__ import annotations

import pytest

# O fixture `cliente`, já autenticado, vem de conftest.py.


@pytest.fixture()
def ano(cliente, conta):
    resposta = cliente.post(
        "/anos",
        json={
            "ano": 2026,
            "saldos_iniciais": [
                {"conta_id": conta["id"], "saldo": "0.97", "guardado": "7867.36"}
            ],
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _lanc(conta, **campos):
    """Monta o corpo de um lançamento com os campos obrigatórios preenchidos."""
    base = {
        "data": "2026-04-06",
        "valor": "10",
        "tipo": "entrada",
        "conta_id": conta["id"],
    }
    base.update(campos)
    return base


class TestAnos:
    def test_cria_e_lista(self, cliente, ano):
        assert ano["ano"] == 2026
        assert cliente.get("/anos").json()[0]["ano"] == 2026

    def test_ano_duplicado_e_rejeitado(self, cliente, ano):
        assert cliente.post("/anos", json={"ano": 2026}).status_code == 409

    def test_resumo_traz_doze_meses(self, cliente, ano):
        resumo = cliente.get("/anos/2026/resumo").json()
        assert len(resumo["meses"]) == 12
        assert resumo["meses"][0]["nome_mes"] == "janeiro"
        assert resumo["meses"][11]["nome_mes"] == "dezembro"

    def test_ano_inexistente_da_404(self, cliente):
        assert cliente.get("/anos/1999/resumo").status_code == 404


class TestContas:
    def test_cria_e_lista_na_ordem_definida(self, cliente):
        cliente.post("/contas", json={"nome": "Nubank", "ordem": 1})
        cliente.post("/contas", json={"nome": "Mercado Pago", "ordem": 0})
        assert [c["nome"] for c in cliente.get("/contas").json()] == [
            "Mercado Pago",
            "Nubank",
        ]

    def test_nome_duplicado_e_rejeitado(self, cliente, conta):
        assert cliente.post("/contas", json={"nome": conta["nome"]}).status_code == 409

    def test_nao_apaga_conta_com_movimentacao(self, cliente, ano, conta):
        cliente.post("/anos/2026/lancamentos", json=_lanc(conta))
        assert cliente.delete(f"/contas/{conta['id']}").status_code == 204
        # Desativada, não removida: o histórico continua íntegro.
        assert cliente.get("/contas").json() == []
        inativas = cliente.get("/contas?incluir_inativas=true").json()
        assert inativas[0]["ativa"] is False

    def test_apaga_conta_sem_uso(self, cliente):
        nova = cliente.post("/contas", json={"nome": "Temporária"}).json()
        assert cliente.delete(f"/contas/{nova['id']}").status_code == 204
        assert cliente.get("/contas?incluir_inativas=true").json() == []


class TestLancamentos:
    def test_cria_lancamento_e_atualiza_o_resumo(self, cliente, ano, conta):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, valor="2000.00", descricao="salário"),
        )
        assert resposta.status_code == 201
        # O mês é derivado da data, não enviado pelo cliente.
        assert resposta.json()["mes"] == 4

        abril = cliente.get("/anos/2026/resumo").json()["meses"][3]
        assert abril["entradas"] == "2000.00"

    def test_data_de_outro_ano_e_rejeitada(self, cliente, ano, conta):
        resposta = cliente.post(
            "/anos/2026/lancamentos", json=_lanc(conta, data="2025-04-06")
        )
        assert resposta.status_code == 422

    def test_rendimento_exige_destino(self, cliente, ano, conta):
        resposta = cliente.post(
            "/anos/2026/lancamentos", json=_lanc(conta, tipo="rendimento")
        )
        assert resposta.status_code == 422

    def test_perda_exige_destino(self, cliente, ano, conta):
        resposta = cliente.post(
            "/anos/2026/lancamentos", json=_lanc(conta, tipo="perda")
        )
        assert resposta.status_code == 422

    def test_categoria_so_em_saida(self, cliente, ano, conta):
        categoria = cliente.post("/categorias", json={"nome": "Comida"}).json()
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, categoria_id=categoria["id"]),
        )
        assert resposta.status_code == 422

    def test_valor_negativo_e_rejeitado(self, cliente, ano, conta):
        resposta = cliente.post("/anos/2026/lancamentos", json=_lanc(conta, valor="-10"))
        assert resposta.status_code == 422

    def test_conta_inexistente_e_rejeitada(self, cliente, ano, conta):
        corpo = _lanc(conta)
        corpo["conta_id"] = 9999
        assert cliente.post("/anos/2026/lancamentos", json=corpo).status_code == 422


class TestTransferencias:
    def test_transferencia_nao_entra_em_entradas_nem_saidas(
        self, cliente, ano, conta, conta2
    ):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(
                conta,
                valor="200",
                tipo="transferencia",
                conta_destino_id=conta2["id"],
            ),
        )
        assert resposta.status_code == 201

        abril = cliente.get("/anos/2026/resumo").json()["meses"][3]
        assert abril["entradas"] == "0.00"
        assert abril["saidas"] == "0.00"
        assert abril["transferido"] == "200.00"

        saldos = {c["nome"]: c["saldo"] for c in abril["por_conta"]}
        assert saldos["Mercado Pago"] == "-199.03"  # 0.97 - 200
        assert saldos["Nubank"] == "200.00"

    def test_transferencia_exige_destino(self, cliente, ano, conta):
        resposta = cliente.post(
            "/anos/2026/lancamentos", json=_lanc(conta, tipo="transferencia")
        )
        assert resposta.status_code == 422

    def test_destino_igual_a_origem_e_rejeitado(self, cliente, ano, conta):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, tipo="transferencia", conta_destino_id=conta["id"]),
        )
        assert resposta.status_code == 422

    def test_conta_destino_so_em_transferencia(self, cliente, ano, conta, conta2):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, conta_destino_id=conta2["id"]),
        )
        assert resposta.status_code == 422

    def test_aparece_ao_filtrar_pelas_duas_contas(self, cliente, ano, conta, conta2):
        cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, tipo="transferencia", conta_destino_id=conta2["id"]),
        )
        origem = cliente.get(f"/anos/2026/lancamentos?conta_id={conta['id']}").json()
        destino = cliente.get(f"/anos/2026/lancamentos?conta_id={conta2['id']}").json()
        assert len(origem) == len(destino) == 1


class TestPerdas:
    def test_perda_no_guardado_nao_vira_gasto(self, cliente, ano, conta):
        cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, valor="80", tipo="perda", destino="guardado"),
        )
        abril = cliente.get("/anos/2026/resumo").json()["meses"][3]
        assert abril["saidas"] == "0.00"
        assert abril["perdas"] == "80.00"
        assert abril["gastos_por_categoria"] == []
        # 7867.36 - 80
        assert abril["guardado_acumulado"] == "7787.36"


class TestArquivamento:
    def test_arquivar_gera_o_ano_seguinte_com_os_saldos(self, cliente, ano, conta):
        cliente.post("/anos/2026/lancamentos", json=_lanc(conta, valor="1000"))
        cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, data="2026-04-07", valor="300", tipo="guardado"),
        )

        assert cliente.post("/anos/2026/arquivar").status_code == 200

        anos = {a["ano"]: a for a in cliente.get("/anos").json()}
        assert anos[2026]["arquivado"] is True
        assert 2027 in anos

        # 0.97 + 1000 - 300 = 700.97 ; 7867.36 + 300 = 8167.36
        saldos = {s["conta_id"]: s for s in anos[2027]["saldos_iniciais"]}
        assert saldos[conta["id"]]["saldo"] == "700.97"
        assert saldos[conta["id"]]["guardado"] == "8167.36"

    def test_corrige_saldos_de_ano_futuro_vazio(self, cliente, ano, conta):
        """Criar 2027 antecipadamente para planejar não pode travar seus saldos
        em zero: ao arquivar 2026, a abertura de 2027 é corrigida."""
        cliente.post("/anos", json={"ano": 2027})
        cliente.post("/anos/2026/lancamentos", json=_lanc(conta, valor="1000"))

        cliente.post("/anos/2026/arquivar")

        anos = {a["ano"]: a for a in cliente.get("/anos").json()}
        saldos = {s["conta_id"]: s for s in anos[2027]["saldos_iniciais"]}
        assert saldos[conta["id"]]["saldo"] == "1000.97"
        assert saldos[conta["id"]]["guardado"] == "7867.36"

    def test_nao_mexe_em_ano_futuro_que_ja_tem_lancamentos(self, cliente, ano, conta):
        cliente.post(
            "/anos",
            json={
                "ano": 2027,
                "saldos_iniciais": [
                    {"conta_id": conta["id"], "saldo": "500", "guardado": "0"}
                ],
            },
        )
        cliente.post(
            "/anos/2027/lancamentos",
            json=_lanc(conta, data="2027-01-05", valor="80"),
        )
        cliente.post("/anos/2026/lancamentos", json=_lanc(conta, valor="1000"))

        cliente.post("/anos/2026/arquivar")

        anos = {a["ano"]: a for a in cliente.get("/anos").json()}
        saldos = {s["conta_id"]: s for s in anos[2027]["saldos_iniciais"]}
        assert saldos[conta["id"]]["saldo"] == "500.00"

    def test_ano_arquivado_recusa_edicao(self, cliente, ano, conta):
        cliente.post("/anos/2026/arquivar")
        resposta = cliente.post("/anos/2026/lancamentos", json=_lanc(conta))
        assert resposta.status_code == 409

    def test_ano_arquivado_continua_legivel(self, cliente, ano):
        cliente.post("/anos/2026/arquivar")
        assert cliente.get("/anos/2026/resumo").status_code == 200


class TestCategorias:
    def test_nao_apaga_categoria_em_uso(self, cliente, ano, conta):
        categoria = cliente.post("/categorias", json={"nome": "Comida"}).json()
        cliente.post(
            "/anos/2026/lancamentos",
            json=_lanc(conta, tipo="saida", categoria_id=categoria["id"]),
        )
        assert cliente.delete(f"/categorias/{categoria['id']}").status_code == 204
        # Foi desativada, não removida: o histórico continua íntegro.
        assert cliente.get("/categorias").json() == []
        inativas = cliente.get("/categorias?incluir_inativas=true").json()
        assert inativas[0]["ativa"] is False

    def test_apaga_categoria_nao_usada(self, cliente):
        categoria = cliente.post("/categorias", json={"nome": "Teste"}).json()
        assert cliente.delete(f"/categorias/{categoria['id']}").status_code == 204
        assert cliente.get("/categorias?incluir_inativas=true").json() == []


class TestGastosFixos:
    def test_lista_vem_ordenada_por_vencimento(self, cliente, ano, conta):
        for descricao, dia in [("Internet", 10), ("Academia", 1), ("Dízimo", 6)]:
            cliente.post(
                "/anos/2026/gastos-fixos",
                json={
                    "descricao": descricao,
                    "valor": "50",
                    "dia_vencimento": dia,
                    "conta_id": conta["id"],
                },
            )
        lista = cliente.get("/anos/2026/gastos-fixos").json()
        assert [g["descricao"] for g in lista] == ["Academia", "Dízimo", "Internet"]

    def test_lista_traz_a_situacao_de_cada_mes(self, cliente, ano, conta):
        """Cobre o joinedload da coleção `meses`, que já quebrou uma vez."""
        gasto = cliente.post(
            "/anos/2026/gastos-fixos",
            json={"descricao": "Internet", "valor": "54.17",
                  "conta_id": conta["id"]},
        ).json()
        cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/4/pagar")
        cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/5/pagar")

        lista = cliente.get("/anos/2026/gastos-fixos").json()
        # Um único gasto, sem duplicação causada pelo join.
        assert len(lista) == 1
        assert {m["mes"]: m["situacao"] for m in lista[0]["meses"]} == {
            4: "pago",
            5: "pago",
        }

    def test_pagar_gera_lancamento_uma_vez_so(self, cliente, ano, conta):
        gasto = cliente.post(
            "/anos/2026/gastos-fixos",
            json={"descricao": "Internet", "valor": "54.17", "dia_vencimento": 10,
                  "conta_id": conta["id"]},
        ).json()

        primeiro = cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/4/pagar")
        assert primeiro.status_code == 201
        assert primeiro.json()["data"] == "2026-04-10"

        segundo = cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/4/pagar")
        assert segundo.json()["id"] == primeiro.json()["id"]

        assert len(cliente.get("/anos/2026/lancamentos?mes=4").json()) == 1

    def test_dia_31_cai_no_ultimo_dia_do_mes(self, cliente, ano, conta):
        gasto = cliente.post(
            "/anos/2026/gastos-fixos",
            json={"descricao": "Aluguel", "valor": "100", "dia_vencimento": 31,
                  "conta_id": conta["id"]},
        ).json()
        resposta = cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/2/pagar")
        assert resposta.json()["data"] == "2026-02-28"

    def test_desfazer_remove_o_lancamento(self, cliente, ano, conta):
        gasto = cliente.post(
            "/anos/2026/gastos-fixos",
            json={"descricao": "Academia", "valor": "120",
                  "conta_id": conta["id"]},
        ).json()
        cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/4/pagar")
        cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/4/desfazer")
        assert cliente.get("/anos/2026/lancamentos?mes=4").json() == []


class TestWishlist:
    def test_total_soma_apenas_os_marcados(self, cliente, ano):
        cliente.post(
            "/anos/2026/wishlist", json={"desejo": "Fone", "valor": "300", "somar": True}
        )
        cliente.post(
            "/anos/2026/wishlist",
            json={"desejo": "Notebook", "valor": "4000", "somar": False},
        )
        total = cliente.get("/anos/2026/wishlist/total").json()
        assert total["total_marcado"] == "300.00"
        assert total["total_geral"] == "4300.00"
        assert total["quantidade_marcada"] == 1
