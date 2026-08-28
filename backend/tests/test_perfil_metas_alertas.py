"""Perfil, metas de poupança e alertas de vencimento — ADR-06."""

from __future__ import annotations

import calendar
from datetime import date

import pytest


@pytest.fixture()
def ano_corrente(cliente, conta):
    """O ano de hoje. Metas e alertas olham para o presente, não para 2026
    fixo — usar um ano fixo faria os testes quebrarem na virada."""
    resposta = cliente.post("/anos", json={"ano": date.today().year})
    assert resposta.status_code in (200, 201), resposta.text
    return resposta.json()


def dia_daqui(dias: int) -> int:
    """Dia do mês daqui a N dias, contanto que não vire o mês.

    Alertas só enxergam o mês corrente, então um teste que caia no mês
    seguinte mediria outra coisa — os que usam isto são pulados perto da
    virada em vez de falharem por motivo errado.
    """
    hoje = date.today()
    alvo = hoje.day + dias
    if alvo > calendar.monthrange(hoje.year, hoje.month)[1]:
        pytest.skip("perto da virada do mês: o vencimento cairia no mês seguinte")
    return alvo


class TestPerfil:
    def test_eu_traz_os_campos_novos(self, cliente):
        corpo = cliente.get("/auth/eu").json()
        assert set(corpo) == {"id", "email", "nome", "alertas_email_ativo"}
        # Quem nunca preencheu continua sendo identificado pelo e-mail.
        assert corpo["nome"] is None
        assert corpo["alertas_email_ativo"] is False

    def test_edita_o_proprio_nome(self, cliente):
        resposta = cliente.patch("/auth/eu", json={"nome": "Kamilly"})
        assert resposta.status_code == 200
        assert resposta.json()["nome"] == "Kamilly"
        assert cliente.get("/auth/eu").json()["nome"] == "Kamilly"

    def test_nome_em_branco_volta_a_nulo(self, cliente):
        """"Nunca preencheu" e "apagou o que tinha" devem ser o mesmo estado."""
        cliente.patch("/auth/eu", json={"nome": "Kamilly"})
        assert cliente.patch("/auth/eu", json={"nome": "   "}).json()["nome"] is None

    def test_atualizacao_e_parcial(self, cliente):
        """Mexer num campo não pode zerar o outro."""
        cliente.patch("/auth/eu", json={"nome": "Kamilly"})
        cliente.patch("/auth/eu", json={"alertas_email_ativo": True})

        corpo = cliente.get("/auth/eu").json()
        assert corpo["nome"] == "Kamilly"
        assert corpo["alertas_email_ativo"] is True

    def test_exige_sessao(self, cliente_sem_login):
        assert cliente_sem_login.patch("/auth/eu", json={"nome": "X"}).status_code == 401


class TestMetasPoupanca:
    def test_meta_com_prazo_exige_data(self, cliente):
        resposta = cliente.post(
            "/metas-poupanca", json={"tipo": "prazo", "valor_alvo": "6000"}
        )
        assert resposta.status_code == 422
        assert "data" in resposta.json()["detail"].lower()

    def test_meta_mensal_recusa_data(self, cliente):
        resposta = cliente.post(
            "/metas-poupanca",
            json={"tipo": "mensal", "valor_alvo": "500", "data_alvo": "2026-12-31"},
        )
        assert resposta.status_code == 422

    def test_os_dois_tipos_convivem(self, cliente):
        """Poupar todo mês e juntar para um objetivo não se excluem (ADR-06)."""
        cliente.post("/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "500"})
        cliente.post(
            "/metas-poupanca",
            json={"tipo": "prazo", "valor_alvo": "6000", "data_alvo": "2030-12-31"},
        )

        ativas = cliente.get("/metas-poupanca/ativas").json()
        assert ativas["mensal"] is not None
        assert ativas["prazo"] is not None

    def test_meta_nova_aposenta_a_anterior_do_mesmo_tipo(self, cliente):
        primeira = cliente.post(
            "/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "300"}
        ).json()
        segunda = cliente.post(
            "/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "500"}
        ).json()

        ativas = cliente.get("/metas-poupanca").json()
        assert [m["id"] for m in ativas] == [segunda["id"]]

        # A antiga vira histórico, não desaparece.
        todas = cliente.get("/metas-poupanca?incluir_inativas=true").json()
        antiga = next(m for m in todas if m["id"] == primeira["id"])
        assert antiga["ativa"] is False

    def test_progresso_vem_do_guardado_real(self, cliente, ano_corrente, conta):
        """O percentual tem de bater com o `guardado` que o resumo do ano
        mostra — é a mesma fonte, e não um segundo cálculo paralelo."""
        hoje = date.today()
        cliente.post(
            f"/anos/{hoje.year}/lancamentos",
            json={
                "data": hoje.isoformat(),
                "valor": "250.00",
                "tipo": "guardado",
                "conta_id": conta["id"],
            },
        )
        cliente.post("/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "500"})

        mensal = cliente.get("/metas-poupanca/ativas").json()["mensal"]
        assert mensal["guardado_no_mes"] == "250.00"
        assert mensal["percentual"] == 50.0

        resumo = cliente.get(f"/anos/{hoje.year}/resumo").json()
        assert resumo["meses"][hoje.month - 1]["guardado_no_mes"] == "250.00"

    def test_sem_meta_ativa_devolve_nulo(self, cliente):
        ativas = cliente.get("/metas-poupanca/ativas").json()
        assert ativas == {"mensal": None, "prazo": None}

    def test_progresso_passa_de_cem_por_cento(self, cliente, ano_corrente, conta):
        """Guardar mais que o alvo é informação, não erro — não trunca em 100."""
        hoje = date.today()
        cliente.post(
            f"/anos/{hoje.year}/lancamentos",
            json={
                "data": hoje.isoformat(),
                "valor": "600.00",
                "tipo": "guardado",
                "conta_id": conta["id"],
            },
        )
        cliente.post("/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "500"})
        assert cliente.get("/metas-poupanca/ativas").json()["mensal"]["percentual"] > 100

    def test_ano_corrente_inexistente_nao_quebra(self, cliente):
        """A meta existe mesmo sem nenhum ano criado — progresso é zero."""
        cliente.post("/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "500"})
        mensal = cliente.get("/metas-poupanca/ativas").json()["mensal"]
        assert mensal["guardado_no_mes"] == "0.00"
        assert mensal["percentual"] == 0.0


class TestAlertas:
    def test_gasto_fixo_perto_de_vencer_aparece(self, cliente, ano_corrente, conta):
        dia = dia_daqui(2)
        cliente.post(
            f"/anos/{date.today().year}/gastos-fixos",
            json={
                "descricao": "Internet",
                "valor": "54.17",
                "dia_vencimento": dia,
                "conta_id": conta["id"],
            },
        )
        alertas = cliente.get("/alertas").json()
        assert len(alertas) == 1
        assert alertas[0] == {
            "tipo": "gasto_fixo",
            "gasto_fixo_id": alertas[0]["gasto_fixo_id"],
            "nome": "Internet",
            "dia_vencimento": dia,
            "dias_restantes": 2,
            "valor": "54.17",
        }

    def test_gasto_fixo_pago_nao_aparece(self, cliente, ano_corrente, conta):
        hoje = date.today()
        gasto = cliente.post(
            f"/anos/{hoje.year}/gastos-fixos",
            json={
                "descricao": "Internet",
                "valor": "54.17",
                "dia_vencimento": dia_daqui(1),
                "conta_id": conta["id"],
            },
        ).json()
        cliente.post(
            f"/anos/{hoje.year}/gastos-fixos/{gasto['id']}/meses/{hoje.month}/pagar"
        )
        assert cliente.get("/alertas").json() == []

    def test_vencimento_fora_da_janela_nao_aparece(self, cliente, ano_corrente, conta):
        """Só o que vence nos próximos dias entra na lista.

        O dia escolhido é sempre um que exista no mês e caia fora da janela —
        à frente quando o mês permite, senão um já passado (vencido também
        fica de fora). Sem isso, o teste seria pulado perto da virada,
        justamente quando essa borda mais importa.
        """
        hoje = date.today()
        ultimo = calendar.monthrange(hoje.year, hoje.month)[1]
        distante = hoje.day + 10
        dia = distante if distante <= ultimo else 1
        if dia == 1 and hoje.day <= 4:
            pytest.skip("começo do mês: todo dia existente cai dentro da janela")

        cliente.post(
            f"/anos/{hoje.year}/gastos-fixos",
            json={
                "descricao": "Longe",
                "valor": "10.00",
                "dia_vencimento": dia,
                "conta_id": conta["id"],
            },
        )
        assert cliente.get("/alertas").json() == []

    def test_fatura_de_cartao_tambem_alerta(self, cliente, ano_corrente):
        dia = dia_daqui(1)
        cartao = cliente.post(
            "/contas",
            json={
                "nome": "Cartão X",
                "tipo": "cartao_credito",
                "dia_vencimento_fatura": dia,
            },
        ).json()

        alertas = cliente.get("/alertas").json()
        assert len(alertas) == 1
        # Nomes de campo próprios do cartão, não os do gasto fixo: em todo o
        # resto da API `dia_vencimento` e `dia_vencimento_fatura` são coisas
        # diferentes, e esta rota não inventa um vocabulário só dela.
        assert alertas[0] == {
            "tipo": "fatura",
            "cartao_id": cartao["id"],
            "nome_cartao": "Cartão X",
            "dia_vencimento_fatura": dia,
            "dias_restantes": 1,
            # O valor da fatura sai do cálculo do mês; o alerta é sobre a data.
            "valor": None,
        }

    def test_ordenado_por_urgencia(self, cliente, ano_corrente, conta):
        ano = date.today().year
        for nome, dias in (("Depois", 3), ("Agora", 0), ("Meio", 1)):
            cliente.post(
                f"/anos/{ano}/gastos-fixos",
                json={
                    "descricao": nome,
                    "valor": "10.00",
                    "dia_vencimento": dia_daqui(dias),
                    "conta_id": conta["id"],
                },
            )
        alertas = cliente.get("/alertas").json()
        assert [a["nome"] for a in alertas] == ["Agora", "Meio", "Depois"]

    def test_ordena_misturando_os_dois_tipos(self, cliente, ano_corrente, conta):
        """A ordenação precisa lidar com os dois formatos ao mesmo tempo.

        Gasto fixo e fatura têm nomes de campo diferentes, e o desempate por
        nome lê de campos distintos — misturar os dois é o caso que quebraria
        se alguém assumisse um formato único.
        """
        ano = date.today().year
        cliente.post(
            f"/anos/{ano}/gastos-fixos",
            json={
                "descricao": "Internet",
                "valor": "54.17",
                "dia_vencimento": dia_daqui(2),
                "conta_id": conta["id"],
            },
        )
        cliente.post(
            "/contas",
            json={
                "nome": "Cartão X",
                "tipo": "cartao_credito",
                "dia_vencimento_fatura": dia_daqui(0),
            },
        )

        alertas = cliente.get("/alertas").json()
        assert [a["tipo"] for a in alertas] == ["fatura", "gasto_fixo"]
        assert [a["dias_restantes"] for a in alertas] == [0, 2]

    def test_sem_ano_criado_devolve_lista_vazia(self, cliente):
        assert cliente.get("/alertas").json() == []

    def test_exige_sessao(self, cliente_sem_login):
        assert cliente_sem_login.get("/alertas").status_code == 401
