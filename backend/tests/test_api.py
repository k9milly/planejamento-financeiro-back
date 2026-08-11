"""Testes de integração da API, contra um banco SQLite temporário."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def cliente(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'teste.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def ano(cliente):
    resposta = cliente.post(
        "/anos",
        json={
            "ano": 2026,
            "saldo_inicial_conta": "0.97",
            "saldo_inicial_guardado": "7867.36",
        },
    )
    assert resposta.status_code == 201
    return resposta.json()


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


class TestLancamentos:
    def test_cria_lancamento_e_atualiza_o_resumo(self, cliente, ano):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={
                "data": "2026-04-06",
                "valor": "2000.00",
                "tipo": "entrada",
                "descricao": "salário",
            },
        )
        assert resposta.status_code == 201
        # O mês é derivado da data, não enviado pelo cliente.
        assert resposta.json()["mes"] == 4

        abril = cliente.get("/anos/2026/resumo").json()["meses"][3]
        assert abril["entradas"] == "2000.00"

    def test_data_de_outro_ano_e_rejeitada(self, cliente, ano):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={"data": "2025-04-06", "valor": "10", "tipo": "entrada"},
        )
        assert resposta.status_code == 422

    def test_rendimento_exige_destino(self, cliente, ano):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={"data": "2026-04-06", "valor": "10", "tipo": "rendimento"},
        )
        assert resposta.status_code == 422

    def test_categoria_so_em_saida(self, cliente, ano):
        categoria = cliente.post("/categorias", json={"nome": "Comida"}).json()
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={
                "data": "2026-04-06",
                "valor": "10",
                "tipo": "entrada",
                "categoria_id": categoria["id"],
            },
        )
        assert resposta.status_code == 422

    def test_valor_negativo_e_rejeitado(self, cliente, ano):
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={"data": "2026-04-06", "valor": "-10", "tipo": "entrada"},
        )
        assert resposta.status_code == 422


class TestArquivamento:
    def test_arquivar_gera_o_ano_seguinte_com_os_saldos(self, cliente, ano):
        cliente.post(
            "/anos/2026/lancamentos",
            json={"data": "2026-04-06", "valor": "1000", "tipo": "entrada"},
        )
        cliente.post(
            "/anos/2026/lancamentos",
            json={"data": "2026-04-07", "valor": "300", "tipo": "guardado"},
        )

        assert cliente.post("/anos/2026/arquivar").status_code == 200

        anos = {a["ano"]: a for a in cliente.get("/anos").json()}
        assert anos[2026]["arquivado"] is True
        assert 2027 in anos
        # 0.97 + 1000 - 300 = 700.97 ; 7867.36 + 300 = 8167.36
        assert anos[2027]["saldo_inicial_conta"] == "700.97"
        assert anos[2027]["saldo_inicial_guardado"] == "8167.36"

    def test_ano_arquivado_recusa_edicao(self, cliente, ano):
        cliente.post("/anos/2026/arquivar")
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={"data": "2026-04-06", "valor": "10", "tipo": "entrada"},
        )
        assert resposta.status_code == 409

    def test_ano_arquivado_continua_legivel(self, cliente, ano):
        cliente.post("/anos/2026/arquivar")
        assert cliente.get("/anos/2026/resumo").status_code == 200


class TestCategorias:
    def test_nao_apaga_categoria_em_uso(self, cliente, ano):
        categoria = cliente.post("/categorias", json={"nome": "Comida"}).json()
        cliente.post(
            "/anos/2026/lancamentos",
            json={
                "data": "2026-04-06",
                "valor": "10",
                "tipo": "saida",
                "categoria_id": categoria["id"],
            },
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
    def test_lista_vem_ordenada_por_vencimento(self, cliente, ano):
        for descricao, dia in [("Internet", 10), ("Academia", 1), ("Dízimo", 6)]:
            cliente.post(
                "/anos/2026/gastos-fixos",
                json={"descricao": descricao, "valor": "50", "dia_vencimento": dia},
            )
        lista = cliente.get("/anos/2026/gastos-fixos").json()
        assert [g["descricao"] for g in lista] == ["Academia", "Dízimo", "Internet"]

    def test_lista_traz_a_situacao_de_cada_mes(self, cliente, ano):
        """Cobre o joinedload da coleção `meses`, que já quebrou uma vez."""
        gasto = cliente.post(
            "/anos/2026/gastos-fixos", json={"descricao": "Internet", "valor": "54.17"}
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

    def test_pagar_gera_lancamento_uma_vez_so(self, cliente, ano):
        gasto = cliente.post(
            "/anos/2026/gastos-fixos",
            json={"descricao": "Internet", "valor": "54.17", "dia_vencimento": 10},
        ).json()

        primeiro = cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/4/pagar")
        assert primeiro.status_code == 201
        assert primeiro.json()["data"] == "2026-04-10"

        segundo = cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/4/pagar")
        assert segundo.json()["id"] == primeiro.json()["id"]

        assert len(cliente.get("/anos/2026/lancamentos?mes=4").json()) == 1

    def test_dia_31_cai_no_ultimo_dia_do_mes(self, cliente, ano):
        gasto = cliente.post(
            "/anos/2026/gastos-fixos",
            json={"descricao": "Aluguel", "valor": "100", "dia_vencimento": 31},
        ).json()
        resposta = cliente.post(f"/anos/2026/gastos-fixos/{gasto['id']}/meses/2/pagar")
        assert resposta.json()["data"] == "2026-02-28"

    def test_desfazer_remove_o_lancamento(self, cliente, ano):
        gasto = cliente.post(
            "/anos/2026/gastos-fixos", json={"descricao": "Academia", "valor": "120"}
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
