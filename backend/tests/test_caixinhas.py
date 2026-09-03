"""Caixinhas por conta e o vínculo delas com metas de poupança (ADR-10).

A regra que amarra tudo: uma caixinha **nomeia** parte do que a conta já tem
guardado, nunca acrescenta dinheiro. Quase todo teste aqui é uma forma de
verificar isso.

Os testes usam o ano corrente porque é contra ele que o guardado da conta é
medido — o mesmo recorte que `GET /metas-poupanca/ativas` já usava.
"""

from __future__ import annotations

from datetime import date

import pytest

HOJE = date.today()
ANO = HOJE.year


@pytest.fixture()
def ano(cliente):
    cliente.post("/anos", json={"ano": ANO})
    return ANO


def guardar(cliente, conta, valor, caixinha_id=None, tipo="guardado"):
    """Manda dinheiro para a reserva — opcionalmente para uma caixinha."""
    corpo = {
        "data": HOJE.isoformat(),
        "valor": str(valor),
        "tipo": tipo,
        "conta_id": conta["id"],
    }
    if caixinha_id is not None:
        corpo["caixinha_id"] = caixinha_id
    return cliente.post(f"/anos/{ANO}/lancamentos", json=corpo)


def criar_caixinha(cliente, conta, nome="Reserva", **extras):
    return cliente.post(f"/contas/{conta['id']}/caixinhas", json={"nome": nome, **extras})


class TestCriacao:
    def test_nasce_zerada(self, cliente, ano, conta):
        resposta = criar_caixinha(cliente, conta, "Fatura do cartão")
        assert resposta.status_code == 201

        caixinha = resposta.json()
        assert caixinha["nome"] == "Fatura do cartão"
        assert caixinha["saldo"] == "0.00"
        assert caixinha["ativa"] is True
        assert caixinha["meta_id"] is None

    def test_lista_so_as_ativas_por_padrao(self, cliente, ano, conta):
        primeira = criar_caixinha(cliente, conta, "Reserva").json()
        criar_caixinha(cliente, conta, "Viagem")
        cliente.delete(f"/contas/{conta['id']}/caixinhas/{primeira['id']}")

        ativas = cliente.get(f"/contas/{conta['id']}/caixinhas").json()
        assert [c["nome"] for c in ativas] == ["Viagem"]

        todas = cliente.get(
            f"/contas/{conta['id']}/caixinhas", params={"incluir_inativas": True}
        ).json()
        assert len(todas) == 2

    def test_cartao_de_credito_nao_tem_caixinha(self, cliente, ano):
        cartao = cliente.post(
            "/contas",
            json={"nome": "Cartão", "tipo": "cartao_credito", "dia_vencimento_fatura": 10},
        ).json()
        resposta = criar_caixinha(cliente, cartao)
        assert resposta.status_code == 422
        assert "reserva" in resposta.json()["detail"]

    def test_conta_inexistente(self, cliente, ano):
        assert cliente.post("/contas/999/caixinhas", json={"nome": "X"}).status_code == 404


class TestSaldoInicial:
    """O caso concreto da Kamilly: dar nome a dinheiro já lançado como ajuste."""

    def test_nomeia_o_que_ja_estava_guardado(self, cliente, ano, conta):
        guardar(cliente, conta, "1000.00")

        caixinha = criar_caixinha(cliente, conta, "Reserva", saldo_inicial="600.00")
        assert caixinha.status_code == 201
        assert caixinha.json()["saldo"] == "600.00"

    def test_nao_inventa_dinheiro_que_a_conta_nao_tem(self, cliente, ano, conta):
        guardar(cliente, conta, "100.00")

        resposta = criar_caixinha(cliente, conta, "Reserva", saldo_inicial="500.00")
        assert resposta.status_code == 422
        # A mensagem precisa dizer quanto há, não só que deu errado.
        assert "100,00" in resposta.json()["detail"]

    def test_duas_caixinhas_juntas_tambem_nao_passam_do_guardado(
        self, cliente, ano, conta
    ):
        """O critério de aceite do plano: o teto considera o que já foi rotulado."""
        guardar(cliente, conta, "1000.00")

        assert criar_caixinha(
            cliente, conta, "Reserva", saldo_inicial="700.00"
        ).status_code == 201

        segunda = criar_caixinha(cliente, conta, "Viagem", saldo_inicial="400.00")
        assert segunda.status_code == 422
        assert "300,00" in segunda.json()["detail"]

    def test_o_teto_e_por_conta(self, cliente, ano, conta, conta2):
        """Guardado numa conta não autoriza caixinha na outra."""
        guardar(cliente, conta, "1000.00")

        resposta = criar_caixinha(cliente, conta2, "Reserva", saldo_inicial="500.00")
        assert resposta.status_code == 422

    def test_nao_pode_ser_negativo(self, cliente, ano, conta):
        assert criar_caixinha(
            cliente, conta, "Reserva", saldo_inicial="-10.00"
        ).status_code == 422

    def test_nao_e_editavel_depois(self, cliente, ano, conta):
        """Mudar o saldo inicial reescreveria o passado sem lançamento nenhum."""
        guardar(cliente, conta, "1000.00")
        caixinha = criar_caixinha(cliente, conta, "Reserva", saldo_inicial="100.00").json()

        cliente.patch(
            f"/contas/{conta['id']}/caixinhas/{caixinha['id']}",
            json={"saldo_inicial": "900.00"},
        )
        atual = cliente.get(f"/contas/{conta['id']}/caixinhas").json()[0]
        assert atual["saldo"] == "100.00"


class TestLancamentoComCaixinha:
    def test_guardado_entra_na_caixinha(self, cliente, ano, conta):
        caixinha = criar_caixinha(cliente, conta).json()
        assert guardar(cliente, conta, "250.00", caixinha["id"]).status_code == 201

        atual = cliente.get(f"/contas/{conta['id']}/caixinhas").json()[0]
        assert atual["saldo"] == "250.00"

    def test_retirado_sai_da_caixinha(self, cliente, ano, conta):
        caixinha = criar_caixinha(cliente, conta).json()
        guardar(cliente, conta, "250.00", caixinha["id"])
        guardar(cliente, conta, "100.00", caixinha["id"], tipo="retirado")

        atual = cliente.get(f"/contas/{conta['id']}/caixinhas").json()[0]
        assert atual["saldo"] == "150.00"

    def test_rendimento_no_guardado_aceita_caixinha(self, cliente, ano, conta):
        caixinha = criar_caixinha(cliente, conta).json()
        resposta = cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": HOJE.isoformat(),
                "valor": "12.34",
                "tipo": "rendimento",
                "destino": "guardado",
                "conta_id": conta["id"],
                "caixinha_id": caixinha["id"],
            },
        )
        assert resposta.status_code == 201
        assert cliente.get(f"/contas/{conta['id']}/caixinhas").json()[0]["saldo"] == "12.34"

    def test_rendimento_na_conta_nao_aceita_caixinha(self, cliente, ano, conta):
        """Se o rendimento caiu no saldo, não há reserva envolvida."""
        caixinha = criar_caixinha(cliente, conta).json()
        resposta = cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": HOJE.isoformat(),
                "valor": "12.34",
                "tipo": "rendimento",
                "destino": "conta",
                "conta_id": conta["id"],
                "caixinha_id": caixinha["id"],
            },
        )
        assert resposta.status_code == 422

    def test_entrada_nao_aceita_caixinha(self, cliente, ano, conta):
        caixinha = criar_caixinha(cliente, conta).json()
        resposta = cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": HOJE.isoformat(),
                "valor": "10.00",
                "tipo": "entrada",
                "conta_id": conta["id"],
                "caixinha_id": caixinha["id"],
            },
        )
        assert resposta.status_code == 422

    def test_caixinha_de_outra_conta_e_recusada(self, cliente, ano, conta, conta2):
        caixinha = criar_caixinha(cliente, conta).json()
        resposta = guardar(cliente, conta2, "50.00", caixinha["id"])
        assert resposta.status_code == 422
        assert "outra conta" in resposta.json()["detail"]

    def test_caixinha_desativada_e_recusada(self, cliente, ano, conta):
        caixinha = criar_caixinha(cliente, conta).json()
        cliente.delete(f"/contas/{conta['id']}/caixinhas/{caixinha['id']}")
        assert guardar(cliente, conta, "50.00", caixinha["id"]).status_code == 422

    def test_sem_caixinha_continua_funcionando(self, cliente, ano, conta):
        """Compatibilidade: o campo é opcional e nada muda para quem não o manda."""
        assert guardar(cliente, conta, "300.00").status_code == 201
        resumo = cliente.get(f"/anos/{ANO}/resumo").json()
        assert resumo["total_guardado"] == "300.00"

    def test_mudar_a_conta_do_lancamento_revalida_a_caixinha(
        self, cliente, ano, conta, conta2
    ):
        """PATCH que troca só a conta deixaria a caixinha apontando para fora."""
        caixinha = criar_caixinha(cliente, conta).json()
        lanc = guardar(cliente, conta, "50.00", caixinha["id"]).json()

        resposta = cliente.patch(
            f"/anos/{ANO}/lancamentos/{lanc['id']}", json={"conta_id": conta2["id"]}
        )
        assert resposta.status_code == 422


class TestTransferencia:
    @pytest.fixture()
    def duas(self, cliente, ano, conta):
        guardar(cliente, conta, "1000.00")
        origem = criar_caixinha(cliente, conta, "Reserva", saldo_inicial="600.00").json()
        destino = criar_caixinha(cliente, conta, "Viagem", saldo_inicial="100.00").json()
        return origem, destino

    def test_move_o_saldo_entre_as_duas(self, cliente, conta, duas):
        origem, destino = duas
        resposta = cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": destino["id"],
                "valor": "250.00",
            },
        )
        assert resposta.status_code == 201
        assert resposta.json()["saldo"] == "350.00"

        saldos = {c["nome"]: c["saldo"] for c in
                  cliente.get(f"/contas/{conta['id']}/caixinhas").json()}
        assert saldos == {"Reserva": "350.00", "Viagem": "350.00"}

    def test_nao_mexe_no_resumo_do_ano(self, cliente, conta, duas):
        """O critério de aceite: o dinheiro não saiu da conta, só trocou de rótulo."""
        origem, destino = duas
        antes = cliente.get(f"/anos/{ANO}/resumo").json()

        cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": destino["id"],
                "valor": "250.00",
            },
        )
        depois = cliente.get(f"/anos/{ANO}/resumo").json()

        assert depois == antes

    def test_aparece_no_historico_de_lancamentos(self, cliente, conta, duas):
        origem, destino = duas
        cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": destino["id"],
                "valor": "250.00",
            },
        )
        lancamentos = cliente.get(
            f"/anos/{ANO}/lancamentos", params={"tipo": "transferencia_caixinha"}
        ).json()

        assert len(lancamentos) == 1
        assert lancamentos[0]["caixinha_id"] == origem["id"]
        assert lancamentos[0]["caixinha_destino_id"] == destino["id"]
        assert lancamentos[0]["descricao"] == "Reserva → Viagem"

    def test_nao_move_mais_do_que_a_origem_tem(self, cliente, conta, duas):
        origem, destino = duas
        resposta = cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": destino["id"],
                "valor": "999.00",
            },
        )
        assert resposta.status_code == 422
        assert "600,00" in resposta.json()["detail"]

    def test_origem_e_destino_precisam_ser_diferentes(self, cliente, conta, duas):
        origem, _ = duas
        resposta = cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": origem["id"],
                "valor": "10.00",
            },
        )
        assert resposta.status_code == 422

    def test_caixinha_de_outra_conta_nao_entra(self, cliente, conta, conta2, duas):
        origem, _ = duas
        de_fora = criar_caixinha(cliente, conta2, "De fora").json()
        resposta = cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": de_fora["id"],
                "valor": "10.00",
            },
        )
        assert resposta.status_code == 404

    def test_valor_precisa_ser_positivo(self, cliente, conta, duas):
        origem, destino = duas
        resposta = cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": destino["id"],
                "valor": "0",
            },
        )
        assert resposta.status_code == 422


class TestDesativacao:
    def test_o_saldo_volta_a_ser_guardado_sem_caixinha(self, cliente, ano, conta):
        """Desativar solta o rótulo, não o dinheiro."""
        guardar(cliente, conta, "1000.00")
        caixinha = criar_caixinha(cliente, conta, "Reserva", saldo_inicial="800.00").json()

        # Com a caixinha ativa, sobram R$ 200 sem rótulo.
        assert criar_caixinha(
            cliente, conta, "Outra", saldo_inicial="300.00"
        ).status_code == 422

        cliente.delete(f"/contas/{conta['id']}/caixinhas/{caixinha['id']}")

        # Desativada, os R$ 800 voltam para o bolo sem rótulo.
        assert criar_caixinha(
            cliente, conta, "Outra", saldo_inicial="900.00"
        ).status_code == 201

    def test_o_resumo_do_ano_nao_muda(self, cliente, ano, conta):
        guardar(cliente, conta, "1000.00")
        caixinha = criar_caixinha(cliente, conta, "Reserva", saldo_inicial="800.00").json()
        antes = cliente.get(f"/anos/{ANO}/resumo").json()

        cliente.delete(f"/contas/{conta['id']}/caixinhas/{caixinha['id']}")
        assert cliente.get(f"/anos/{ANO}/resumo").json() == antes

    def test_conta_com_caixinha_e_desativada_em_vez_de_apagada(self, cliente, ano, conta):
        criar_caixinha(cliente, conta)
        cliente.delete(f"/contas/{conta['id']}")

        contas = cliente.get("/contas", params={"incluir_inativas": True}).json()
        assert [c["ativa"] for c in contas if c["id"] == conta["id"]] == [False]


class TestVinculoComMeta:
    @pytest.fixture()
    def meta_prazo(self, cliente):
        return cliente.post(
            "/metas-poupanca",
            json={
                "tipo": "prazo",
                "valor_alvo": "1000.00",
                "data_alvo": date(ANO, 12, 31).isoformat(),
            },
        ).json()

    def test_meta_com_prazo_passa_a_ler_o_saldo_da_caixinha(
        self, cliente, ano, conta, meta_prazo
    ):
        guardar(cliente, conta, "900.00")
        criar_caixinha(
            cliente, conta, "Reserva", saldo_inicial="400.00", meta_id=meta_prazo["id"]
        )

        prazo = cliente.get("/metas-poupanca/ativas").json()["prazo"]
        assert prazo["guardado_acumulado"] == "400.00"
        assert prazo["percentual"] == 40.0

    def test_sem_caixinha_vinculada_nada_muda(self, cliente, ano, conta, meta_prazo):
        """O comportamento do ADR-06 continua valendo para quem não usa caixinha."""
        guardar(cliente, conta, "900.00")
        criar_caixinha(cliente, conta, "Sem vínculo", saldo_inicial="400.00")

        prazo = cliente.get("/metas-poupanca/ativas").json()["prazo"]
        assert prazo["guardado_acumulado"] == "900.00"

    def test_caixinha_desativada_para_de_contar_para_a_meta(
        self, cliente, ano, conta, meta_prazo
    ):
        guardar(cliente, conta, "900.00")
        caixinha = criar_caixinha(
            cliente, conta, "Reserva", saldo_inicial="400.00", meta_id=meta_prazo["id"]
        ).json()
        cliente.delete(f"/contas/{conta['id']}/caixinhas/{caixinha['id']}")

        prazo = cliente.get("/metas-poupanca/ativas").json()["prazo"]
        # Volta ao cálculo do ADR-06, sobre o guardado da conta inteira.
        assert prazo["guardado_acumulado"] == "900.00"

    def test_meta_mensal_conta_o_que_entrou_no_mes_e_nao_o_saldo(
        self, cliente, ano, conta
    ):
        """O saldo herdado de antes não pode dar a meta do mês por cumprida."""
        cliente.post(
            "/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "500.00"}
        )
        guardar(cliente, conta, "5000.00")
        meta = cliente.get("/metas-poupanca/ativas").json()["mensal"]
        caixinha = criar_caixinha(
            cliente, conta, "Reserva", saldo_inicial="4000.00", meta_id=meta["id"]
        ).json()

        # O saldo é 4000, mas nada entrou na caixinha depois de ela existir.
        mensal = cliente.get("/metas-poupanca/ativas").json()["mensal"]
        assert mensal["guardado_no_mes"] == "0.00"

        guardar(cliente, conta, "200.00", caixinha["id"])
        mensal = cliente.get("/metas-poupanca/ativas").json()["mensal"]
        assert mensal["guardado_no_mes"] == "200.00"

    def test_transferencia_entre_caixinhas_da_meta_nao_infla_o_mensal(
        self, cliente, ano, conta
    ):
        """Realocar não é guardar: o mês não pode ganhar dinheiro por isso."""
        cliente.post("/metas-poupanca", json={"tipo": "mensal", "valor_alvo": "500.00"})
        meta = cliente.get("/metas-poupanca/ativas").json()["mensal"]
        guardar(cliente, conta, "1000.00")

        origem = criar_caixinha(
            cliente, conta, "Reserva", saldo_inicial="600.00", meta_id=meta["id"]
        ).json()
        destino = criar_caixinha(
            cliente, conta, "Viagem", saldo_inicial="100.00", meta_id=meta["id"]
        ).json()

        cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": origem["id"],
                "caixinha_destino_id": destino["id"],
                "valor": "300.00",
            },
        )

        mensal = cliente.get("/metas-poupanca/ativas").json()["mensal"]
        assert mensal["guardado_no_mes"] == "0.00"

    def test_meta_desativada_nao_pode_ser_vinculada(self, cliente, ano, conta, meta_prazo):
        cliente.delete(f"/metas-poupanca/{meta_prazo['id']}")
        resposta = criar_caixinha(cliente, conta, "Reserva", meta_id=meta_prazo["id"])
        assert resposta.status_code == 422

    def test_meta_inexistente(self, cliente, ano, conta):
        assert criar_caixinha(cliente, conta, "Reserva", meta_id=999).status_code == 422

    def test_desvincula_com_null_explicito(self, cliente, ano, conta, meta_prazo):
        caixinha = criar_caixinha(
            cliente, conta, "Reserva", meta_id=meta_prazo["id"]
        ).json()

        atualizada = cliente.patch(
            f"/contas/{conta['id']}/caixinhas/{caixinha['id']}", json={"meta_id": None}
        ).json()
        assert atualizada["meta_id"] is None

    def test_patch_sem_o_campo_preserva_o_vinculo(self, cliente, ano, conta, meta_prazo):
        """Campo ausente e campo nulo querem dizer coisas diferentes aqui."""
        caixinha = criar_caixinha(
            cliente, conta, "Reserva", meta_id=meta_prazo["id"]
        ).json()

        atualizada = cliente.patch(
            f"/contas/{conta['id']}/caixinhas/{caixinha['id']}", json={"nome": "Outro"}
        ).json()
        assert atualizada["meta_id"] == meta_prazo["id"]
        assert atualizada["nome"] == "Outro"


class TestNuncaFicaNegativa:
    """Uma caixinha é uma parte do que a conta guardou, não um limite de crédito.

    Como o saldo é derivado, o saldo negativo é alcançável por três caminhos
    diferentes — e checar só a operação que a pessoa está fazendo cobriria
    apenas o primeiro. Por isso a trava olha o **resultado**, depois da mudança
    já estar aplicada na sessão e antes do commit.
    """

    @pytest.fixture()
    def com_saldo(self, cliente, ano, conta):
        """Uma caixinha com R$ 500, alimentada por um lançamento de verdade."""
        caixinha = criar_caixinha(cliente, conta, "Reserva").json()
        deposito = guardar(cliente, conta, "500.00", caixinha["id"]).json()
        return caixinha, deposito

    def _saldo(self, cliente, conta):
        return cliente.get(f"/contas/{conta['id']}/caixinhas").json()[0]["saldo"]

    # --- caminho 1: retirar mais do que a caixinha tem ---
    def test_retirar_mais_do_que_tem_e_recusado(self, cliente, ano, conta, com_saldo):
        caixinha, _ = com_saldo
        resposta = guardar(cliente, conta, "900.00", caixinha["id"], tipo="retirado")

        assert resposta.status_code == 422
        assert "negativa" in resposta.json()["detail"]
        assert "400,00" in resposta.json()["detail"]
        assert self._saldo(cliente, conta) == "500.00"

    def test_retirar_o_saldo_exato_e_permitido(self, cliente, ano, conta, com_saldo):
        """A trava é sobre ficar negativa, não sobre esvaziar."""
        caixinha, _ = com_saldo
        assert guardar(
            cliente, conta, "500.00", caixinha["id"], tipo="retirado"
        ).status_code == 201
        assert self._saldo(cliente, conta) == "0.00"

    def test_perda_no_guardado_tambem_respeita(self, cliente, ano, conta, com_saldo):
        caixinha, _ = com_saldo
        resposta = cliente.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "data": HOJE.isoformat(),
                "valor": "900.00",
                "tipo": "perda",
                "destino": "guardado",
                "conta_id": conta["id"],
                "caixinha_id": caixinha["id"],
            },
        )
        assert resposta.status_code == 422

    # --- caminho 2: apagar o lançamento que financiou uma saída anterior ---
    def test_apagar_o_deposito_que_financiou_a_retirada_e_recusado(
        self, cliente, ano, conta, com_saldo
    ):
        caixinha, deposito = com_saldo
        guardar(cliente, conta, "500.00", caixinha["id"], tipo="retirado")

        resposta = cliente.delete(f"/anos/{ANO}/lancamentos/{deposito['id']}")
        assert resposta.status_code == 422
        assert "negativa" in resposta.json()["detail"]

        # Nada foi gravado: o depósito continua na lista.
        ids = [l["id"] for l in cliente.get(f"/anos/{ANO}/lancamentos").json()]
        assert deposito["id"] in ids
        assert self._saldo(cliente, conta) == "0.00"

    def test_apagar_o_deposito_e_permitido_se_a_caixinha_aguenta(
        self, cliente, ano, conta, com_saldo
    ):
        caixinha, deposito = com_saldo
        guardar(cliente, conta, "200.00", caixinha["id"])

        # Sobram R$ 200 sem o depósito de 500 — nada fica negativo.
        assert cliente.delete(
            f"/anos/{ANO}/lancamentos/{deposito['id']}"
        ).status_code == 204
        assert self._saldo(cliente, conta) == "200.00"

    # --- caminho 3: editar um lançamento já gravado ---
    def test_aumentar_o_valor_de_uma_retirada_e_recusado(
        self, cliente, ano, conta, com_saldo
    ):
        caixinha, _ = com_saldo
        retirada = guardar(
            cliente, conta, "100.00", caixinha["id"], tipo="retirado"
        ).json()

        resposta = cliente.patch(
            f"/anos/{ANO}/lancamentos/{retirada['id']}", json={"valor": "900.00"}
        )
        assert resposta.status_code == 422
        assert self._saldo(cliente, conta) == "400.00"

    def test_virar_um_guardado_em_retirada_e_recusado(self, cliente, ano, conta):
        """O tipo muda o sinal: o mesmo lançamento passa a tirar em vez de pôr."""
        caixinha = criar_caixinha(cliente, conta, "Reserva").json()
        deposito = guardar(cliente, conta, "500.00", caixinha["id"]).json()

        resposta = cliente.patch(
            f"/anos/{ANO}/lancamentos/{deposito['id']}", json={"tipo": "retirado"}
        )
        assert resposta.status_code == 422
        assert self._saldo(cliente, conta) == "500.00"

    def test_mover_o_deposito_para_outra_caixinha_e_recusado(
        self, cliente, ano, conta, com_saldo
    ):
        """A caixinha que perde o depósito também precisa ser conferida."""
        caixinha, deposito = com_saldo
        guardar(cliente, conta, "500.00", caixinha["id"], tipo="retirado")
        outra = criar_caixinha(cliente, conta, "Viagem").json()

        resposta = cliente.patch(
            f"/anos/{ANO}/lancamentos/{deposito['id']}",
            json={"caixinha_id": outra["id"]},
        )
        assert resposta.status_code == 422
        assert "Reserva" in resposta.json()["detail"]

    # --- a transferência já era conferida, mas a regra vale igual ---
    def test_transferencia_nao_zera_por_baixo(self, cliente, ano, conta, com_saldo):
        caixinha, _ = com_saldo
        destino = criar_caixinha(cliente, conta, "Viagem").json()

        resposta = cliente.post(
            f"/contas/{conta['id']}/caixinhas/transferir",
            json={
                "caixinha_origem_id": caixinha["id"],
                "caixinha_destino_id": destino["id"],
                "valor": "900.00",
            },
        )
        assert resposta.status_code == 422
        assert self._saldo(cliente, conta) == "500.00"

    # --- lançamentos sem caixinha não são afetados pela trava ---
    def test_lancamento_sem_caixinha_continua_livre(self, cliente, ano, conta):
        """A trava é sobre caixinha; quem não usa caixinha não muda de comportamento."""
        assert guardar(cliente, conta, "100.00").status_code == 201
        assert guardar(cliente, conta, "900.00", tipo="retirado").status_code == 201
