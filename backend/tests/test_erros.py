"""Formato de erro da API — ADR-01.

Toda resposta de erro, venha de onde vier, tem `detail` com uma frase em
português pronta para exibir. Estes testes existem porque a garantia é
justamente essa: quem consome a API lê sempre o mesmo campo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


@pytest.fixture()
def ano(cliente, conta):
    """Ano de trabalho. Repetida de `test_api.py` de propósito: fixture de um
    módulo de teste não é visível nos outros."""
    resposta = cliente.post("/anos", json={"ano": 2026})
    assert resposta.status_code in (200, 201), resposta.text
    return resposta.json()


@pytest.fixture()
def cliente_que_deixa_estourar(sessao_teste, usuario):
    """Cliente autenticado que devolve o 500 em vez de re-levantar a exceção.

    Por padrão o `TestClient` re-levanta o erro do servidor, o que é útil para
    depurar mas impede verificar o que o navegador receberia.
    """

    def _get_db():
        db = sessao_teste()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        token = c.post("/auth/login", json=usuario).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    app.dependency_overrides.clear()


class TestErroDeValidacao:
    def test_campo_faltando_vira_frase_unica(self, cliente, ano, conta):
        """O 422 do Pydantic é uma lista de objetos em inglês; aqui vira frase."""
        resposta = cliente.post("/anos/2026/lancamentos", json={"tipo": "saida"})
        assert resposta.status_code == 422

        corpo = resposta.json()
        assert isinstance(corpo["detail"], str), "detail tem de ser texto, não lista"
        assert corpo["detail"], "detail não pode vir vazio"

    def test_campos_apontam_o_que_falhou(self, cliente, ano, conta):
        """`campos` é o extra para o formulário destacar o campo errado."""
        resposta = cliente.post("/anos/2026/lancamentos", json={"tipo": "saida"})
        campos = resposta.json()["campos"]

        assert campos, "sem `campos` o formulário não sabe o que destacar"
        assert {"campo", "mensagem"} <= set(campos[0])
        # 'body' (a origem do erro) não interessa a quem preenche o formulário.
        assert not campos[0]["campo"].startswith("body")
        assert "valor" in {c["campo"] for c in campos}

    def test_regra_de_negocio_perde_o_prefixo_do_pydantic(self, cliente, ano, conta):
        """Regra escrita em `model_validator` já vem como frase pronta.

        O Pydantic prefixa essas mensagens com "Value error, " — mostrar isso
        ao usuário seria vazar vocabulário de biblioteca na tela.
        """
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={
                "data": "2026-08-10",
                "valor": "50",
                "tipo": "transferencia",  # exige conta_destino_id, que falta
                "conta_id": conta["id"],
            },
        )
        assert resposta.status_code == 422

        detail = resposta.json()["detail"]
        assert not detail.startswith("Value error"), detail
        assert "destino" in detail.lower(), detail

    def test_erro_de_negocio_continua_como_estava(self, cliente, ano, conta):
        """`HTTPException` já respondia no formato certo — não podia mudar."""
        resposta = cliente.post(
            "/anos/2026/lancamentos",
            json={
                "data": "2026-08-10",
                "valor": "50",
                "tipo": "saida",
                "forma_pagamento": "credito",  # crédito exige cartão
                "conta_id": conta["id"],
            },
        )
        assert resposta.status_code == 422
        assert isinstance(resposta.json()["detail"], str)


class TestErroInesperado:
    """O cenário do ADR-01: bug ou falha de banco no meio de uma requisição.

    A falha é injetada no `get_db` — depois do login, para a sessão já existir —
    porque é o ponto por onde toda rota de dado passa e simula de perto o caso
    real de "o banco caiu".
    """

    @staticmethod
    def _derrubar_banco(cliente):
        def _explode():
            raise RuntimeError("banco caiu no meio da consulta")
            yield  # nunca alcançado; mantém a assinatura de dependência

        app.dependency_overrides[get_db] = _explode
        return cliente

    def test_bug_vira_500_com_mensagem_generica(self, cliente_que_deixa_estourar):
        """Um erro não previsto não pode vazar traceback nem quebrar o formato."""
        cliente = self._derrubar_banco(cliente_que_deixa_estourar)

        resposta = cliente.get("/categorias")
        assert resposta.status_code == 500

        assert resposta.json()["detail"] == "Erro interno. Tente novamente em instantes."
        # A causa real vai para o log do servidor, nunca para a resposta.
        assert "banco caiu" not in resposta.text
        assert "Traceback" not in resposta.text

    def test_500_chega_ao_navegador_com_cabecalho_cors(
        self, cliente_que_deixa_estourar
    ):
        """Sem CORS no 500, o navegador esconde a mensagem atrás de um erro de CORS.

        É o caso em que a mensagem mais importa — e o mais fácil de errar, porque
        a resposta de erro pode ser montada acima do middleware de CORS na pilha.
        """
        cliente = self._derrubar_banco(cliente_que_deixa_estourar)

        resposta = cliente.get(
            "/categorias", headers={"Origin": "http://localhost:5173"}
        )
        assert resposta.status_code == 500
        assert "access-control-allow-origin" in {
            k.lower() for k in resposta.headers
        }, "o navegador vai reportar erro de CORS em vez de mostrar a mensagem"

    def test_campos_tambem_perdem_o_prefixo(self, cliente):
        """A limpeza vale para `campos`, não só para `detail`.

        Quem usa a lista para destacar o campo errado mostra a mesma frase de
        quem lê só o `detail` — sem "Value error," aparecendo em um e não no
        outro.
        """
        resposta = cliente.post(
            "/metas-poupanca", json={"tipo": "prazo", "valor_alvo": "6000"}
        )
        assert resposta.status_code == 422

        corpo = resposta.json()
        assert not corpo["detail"].startswith("Value error")
        for campo in corpo["campos"]:
            assert not campo["mensagem"].startswith("Value error"), campo
