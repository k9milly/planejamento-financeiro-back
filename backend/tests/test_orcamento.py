"""Orçamento por categoria: o limite mensal e a preferência de exibição (ADR-11).

O que este ADR acrescenta é só **metade** do orçamento — a intenção. A outra
metade, o gasto real por categoria, já existia e não foi tocada; o último teste
daqui verifica que as duas metades se encontram, que é o que a tela precisa.
"""

from __future__ import annotations

from datetime import date

import pytest

# Os testes precisam do mesmo "hoje" que a aplicação usa: o do fuso de São
# Paulo, não o do relógio da máquina. O CI roda em UTC, então entre 21h e
# meia-noite no Brasil os dois discordam em um dia — e uma suíte que usasse
# `date.today()` falharia só nesse intervalo (ver `app/services/tempo.py`).
from app.services.tempo import hoje

HOJE = hoje()
ANO = HOJE.year


@pytest.fixture()
def ano(cliente):
    cliente.post("/anos", json={"ano": ANO})
    return ANO


class TestLimiteDaCategoria:
    def test_categoria_nasce_sem_limite(self, cliente):
        """Sem orçamento é o normal, não uma pendência."""
        categoria = cliente.post("/categorias", json={"nome": "Comida"}).json()
        assert categoria["limite_mensal"] is None

    def test_cria_ja_com_limite(self, cliente):
        categoria = cliente.post(
            "/categorias", json={"nome": "Comida", "limite_mensal": "600.00"}
        ).json()
        assert categoria["limite_mensal"] == "600.00"

    def test_define_o_limite_depois(self, cliente):
        categoria = cliente.post("/categorias", json={"nome": "Comida"}).json()

        atualizada = cliente.patch(
            f"/categorias/{categoria['id']}", json={"limite_mensal": "600.00"}
        ).json()
        assert atualizada["limite_mensal"] == "600.00"

    def test_lista_devolve_o_limite(self, cliente):
        cliente.post("/categorias", json={"nome": "Comida", "limite_mensal": "600.00"})
        cliente.post("/categorias", json={"nome": "Lazer"})

        limites = {
            c["nome"]: c["limite_mensal"] for c in cliente.get("/categorias").json()
        }
        assert limites == {"Comida": "600.00", "Lazer": None}

    def test_null_explicito_remove_o_limite(self, cliente, ano, conta):
        """O critério de aceite: remover o limite não apaga a categoria."""
        categoria = cliente.post(
            "/categorias", json={"nome": "Comida", "limite_mensal": "600.00"}
        ).json()
        gasto = cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": HOJE.isoformat(),
                "valor": "50.00",
                "tipo": "saida",
                "conta_id": conta["id"],
                "categoria_id": categoria["id"],
            },
        )
        assert gasto.status_code == 201

        sem_limite = cliente.patch(
            f"/categorias/{categoria['id']}", json={"limite_mensal": None}
        ).json()

        assert sem_limite["limite_mensal"] is None
        assert sem_limite["ativa"] is True
        assert sem_limite["nome"] == "Comida"
        # E o lançamento histórico continua onde estava.
        assert len(cliente.get(f"/anos/{ANO}/lancamentos").json()) == 1

    def test_patch_sem_o_campo_preserva_o_limite(self, cliente):
        """Campo ausente e campo nulo querem dizer coisas diferentes."""
        categoria = cliente.post(
            "/categorias", json={"nome": "Comida", "limite_mensal": "600.00"}
        ).json()

        atualizada = cliente.patch(
            f"/categorias/{categoria['id']}", json={"cor": "#ff0000"}
        ).json()
        assert atualizada["limite_mensal"] == "600.00"
        assert atualizada["cor"] == "#ff0000"

    def test_limite_zero_e_recusado(self, cliente):
        """Um teto de zero não significa nada — quem não tem orçamento usa null."""
        resposta = cliente.post(
            "/categorias", json={"nome": "Comida", "limite_mensal": "0"}
        )
        assert resposta.status_code == 422

    def test_limite_negativo_e_recusado(self, cliente):
        resposta = cliente.post(
            "/categorias", json={"nome": "Comida", "limite_mensal": "-10.00"}
        )
        assert resposta.status_code == 422

    def test_desativar_a_categoria_nao_mexe_no_limite(self, cliente):
        categoria = cliente.post(
            "/categorias", json={"nome": "Comida", "limite_mensal": "600.00"}
        ).json()
        cliente.patch(f"/categorias/{categoria['id']}", json={"ativa": False})

        inativa = [
            c
            for c in cliente.get(
                "/categorias", params={"incluir_inativas": True}
            ).json()
            if c["id"] == categoria["id"]
        ][0]
        assert inativa["limite_mensal"] == "600.00"


class TestPreferenciaDeExibicao:
    def test_nasce_ligada(self, cliente):
        """Inclusive para quem já existia antes do campo — vem do server_default."""
        assert cliente.get("/auth/eu").json()["mostrar_orcamento_categoria"] is True

    def test_desliga_e_liga(self, cliente):
        desligada = cliente.patch(
            "/auth/eu", json={"mostrar_orcamento_categoria": False}
        ).json()
        assert desligada["mostrar_orcamento_categoria"] is False
        assert cliente.get("/auth/eu").json()["mostrar_orcamento_categoria"] is False

        religada = cliente.patch(
            "/auth/eu", json={"mostrar_orcamento_categoria": True}
        ).json()
        assert religada["mostrar_orcamento_categoria"] is True

    def test_desligar_nao_apaga_limite_nenhum(self, cliente):
        """É preferência de exibição, não de dado — esconder não é apagar."""
        cliente.post("/categorias", json={"nome": "Comida", "limite_mensal": "600.00"})
        cliente.patch("/auth/eu", json={"mostrar_orcamento_categoria": False})

        assert cliente.get("/categorias").json()[0]["limite_mensal"] == "600.00"

    def test_nao_atrapalha_os_outros_campos_do_perfil(self, cliente):
        """`PATCH /auth/eu` é o mesmo endpoint do nome e do alerta (ADR-06)."""
        cliente.patch("/auth/eu", json={"nome": "Kamilly"})
        cliente.patch("/auth/eu", json={"mostrar_orcamento_categoria": False})

        eu = cliente.get("/auth/eu").json()
        assert eu["nome"] == "Kamilly"
        assert eu["mostrar_orcamento_categoria"] is False
        assert eu["alertas_email_ativo"] is False


class TestAsDuasMetadesSeEncontram:
    """A tela precisa do limite (deste ADR) e do gasto real (que já existia)."""

    def test_limite_e_gasto_real_batem_pela_categoria(self, cliente, ano, conta):
        comida = cliente.post(
            "/categorias", json={"nome": "Comida", "limite_mensal": "600.00"}
        ).json()

        for valor in ("100.00", "27.74"):
            cliente.post(
                f"/anos/{ANO}/lancamentos",
                json={
                    "data": HOJE.isoformat(),
                    "valor": valor,
                    "tipo": "saida",
                    "conta_id": conta["id"],
                    "categoria_id": comida["id"],
                },
            )

        # Metade 1: o limite, de `GET /categorias`.
        limite = cliente.get("/categorias").json()[0]["limite_mensal"]
        assert limite == "600.00"

        # Metade 2: o gasto real, da agregação que já existia — sem endpoint novo.
        resumo = cliente.get(f"/anos/{ANO}/resumo").json()
        do_mes = resumo["meses"][HOJE.month - 1]["gastos_por_categoria"]
        gasto = {g["categoria"]: g["total"] for g in do_mes}["Comida"]
        assert gasto == "127.74"

        # A tela divide um pelo outro. O backend não calcula essa porcentagem.
        assert "percentual_do_limite" not in do_mes[0]

    def test_gasto_sem_limite_continua_aparecendo(self, cliente, ano, conta):
        """Categoria sem orçamento não some do relatório de gastos."""
        lazer = cliente.post("/categorias", json={"nome": "Lazer"}).json()
        cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": HOJE.isoformat(),
                "valor": "17.00",
                "tipo": "saida",
                "conta_id": conta["id"],
                "categoria_id": lazer["id"],
            },
        )

        resumo = cliente.get(f"/anos/{ANO}/resumo").json()
        do_mes = resumo["meses"][HOJE.month - 1]["gastos_por_categoria"]
        assert {g["categoria"]: g["total"] for g in do_mes} == {"Lazer": "17.00"}
