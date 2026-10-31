"""O connect token da Pluggy, contra uma Pluggy falsa.

Nenhum teste aqui fala com a Pluggy de verdade: o `httpx` é desviado para um
transporte falso, que responde o que a API deles responderia. Assim a suíte
não depende de rede, de credencial nem de o serviço estar no ar — e, de
quebra, dá para testar o caminho do erro, que contra a API real seria difícil
de provocar de propósito.

As formas das duas chamadas foram conferidas lendo o SDK oficial:

    POST /auth           {clientId, clientSecret}   -> {apiKey}
    POST /connect_token  {options: {clientUserId}}  -> {accessToken}
"""

from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.models import Usuario

CHAVE_FALSA = "chave-de-duas-horas"
TOKEN_FALSO = "token-do-widget"


class PluggyFalsa:
    """Responde como a Pluggy e guarda o que recebeu, para o teste conferir."""

    def __init__(self, *, status_auth: int = 200, status_token: int = 200):
        self.status_auth = status_auth
        self.status_token = status_token
        self.pedidos: list[tuple[str, dict]] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        import json

        corpo = json.loads(pedido.content) if pedido.content else {}
        self.pedidos.append((pedido.url.path, corpo))

        if pedido.url.path == "/auth":
            if self.status_auth != 200:
                return httpx.Response(self.status_auth, json={"message": "nope"})
            return httpx.Response(200, json={"apiKey": CHAVE_FALSA})

        if pedido.url.path == "/connect_token":
            if self.status_token != 200:
                return httpx.Response(self.status_token, json={"message": "nope"})
            assert pedido.headers["X-API-KEY"] == CHAVE_FALSA
            return httpx.Response(200, json={"accessToken": TOKEN_FALSO})

        return httpx.Response(404)


@pytest.fixture()
def pluggy(monkeypatch):
    """Credenciais de mentira e `httpx` desviado para a Pluggy falsa."""
    monkeypatch.setattr(settings, "pluggy_client_id", "id-de-teste")
    monkeypatch.setattr(settings, "pluggy_client_secret", "segredo-de-teste")

    falsa = PluggyFalsa()
    original = httpx.Client.__init__

    def com_transporte_falso(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(falsa)
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", com_transporte_falso)
    return falsa


class TestConnectToken:
    def test_devolve_o_token_do_widget(self, cliente, pluggy):
        resposta = cliente.post("/openfinance/connect-token")
        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"access_token": TOKEN_FALSO}

    def test_fala_com_a_pluggy_na_ordem_e_na_forma_certas(self, cliente, pluggy):
        cliente.post("/openfinance/connect-token")

        caminhos = [caminho for caminho, _ in pluggy.pedidos]
        assert caminhos == ["/auth", "/connect_token"]

        _, corpo_auth = pluggy.pedidos[0]
        assert corpo_auth == {
            "clientId": "id-de-teste",
            "clientSecret": "segredo-de-teste",
        }

        _, corpo_token = pluggy.pedidos[1]
        # `clientUserId` vai **dentro de options**. O exemplo que circula por
        # aí manda no corpo raiz, e a API não o lê lá.
        assert "options" in corpo_token
        assert corpo_token["options"]["clientUserId"].startswith("espaco-")

    def test_o_identificador_e_o_do_espaco(self, cliente, pluggy, sessao_teste):
        """A conexão é do espaço, não da pessoa (ADR-15).

        Um casal que divide o controle divide o banco conectado; por usuário,
        a conexão sumiria da tela do outro membro.
        """
        db = sessao_teste()
        try:
            espaco_id = db.query(Usuario).one().espaco_atual_id
        finally:
            db.close()

        cliente.post("/openfinance/connect-token")
        _, corpo = pluggy.pedidos[1]
        assert corpo["options"]["clientUserId"] == f"espaco-{espaco_id}"

    def test_nenhuma_credencial_vaza_na_resposta(self, cliente, pluggy):
        """O que volta ao navegador é só o token do widget.

        O `clientSecret` nunca pode atravessar — é o motivo inteiro de esta
        rota existir no servidor em vez de o frontend chamar a Pluggy.
        """
        resposta = cliente.post("/openfinance/connect-token")
        texto = resposta.text
        assert "segredo-de-teste" not in texto
        assert "id-de-teste" not in texto
        assert CHAVE_FALSA not in texto

    def test_exige_sessao(self, cliente_sem_login, pluggy):
        assert cliente_sem_login.post("/openfinance/connect-token").status_code == 401

    def test_sem_espaco_escolhido_recusa(self, cliente, pluggy, sessao_teste):
        db = sessao_teste()
        try:
            db.query(Usuario).one().espaco_atual_id = None
            db.commit()
        finally:
            db.close()

        resposta = cliente.post("/openfinance/connect-token")
        assert resposta.status_code == 409
        assert "espaço" in resposta.json()["detail"]
        # E não chegou a incomodar a Pluggy por algo que já se sabia inválido.
        assert pluggy.pedidos == []


class TestQuandoDaErrado:
    def test_sem_credenciais_responde_503(self, cliente, monkeypatch):
        """Instalação sem open finance não derruba o resto do app.

        As credenciais nascem vazias de propósito: quem não usa banco
        conectado continua importando extrato por arquivo, e a aplicação sobe
        normalmente.
        """
        monkeypatch.setattr(settings, "pluggy_client_id", "")
        monkeypatch.setattr(settings, "pluggy_client_secret", "")

        resposta = cliente.post("/openfinance/connect-token")
        assert resposta.status_code == 503
        assert "não está configurado" in resposta.json()["detail"]

    def test_credencial_errada_vira_mensagem_que_ajuda(self, cliente, monkeypatch):
        monkeypatch.setattr(settings, "pluggy_client_id", "id-errado")
        monkeypatch.setattr(settings, "pluggy_client_secret", "segredo-errado")

        falsa = PluggyFalsa(status_auth=403)
        original = httpx.Client.__init__
        monkeypatch.setattr(
            httpx.Client,
            "__init__",
            lambda self, *a, **k: original(
                self, *a, **{**k, "transport": httpx.MockTransport(falsa)}
            ),
        )

        resposta = cliente.post("/openfinance/connect-token")
        assert resposta.status_code == 502
        assert "PLUGGY_CLIENT_ID" in resposta.json()["detail"]

    def test_pluggy_fora_do_ar_vira_502(self, cliente, monkeypatch):
        """502 e não 500: o defeito é de quem respondeu lá fora."""
        monkeypatch.setattr(settings, "pluggy_client_id", "id-de-teste")
        monkeypatch.setattr(settings, "pluggy_client_secret", "segredo-de-teste")

        def recusa(_pedido: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sem rota para o host")

        original = httpx.Client.__init__
        monkeypatch.setattr(
            httpx.Client,
            "__init__",
            lambda self, *a, **k: original(
                self, *a, **{**k, "transport": httpx.MockTransport(recusa)}
            ),
        )

        resposta = cliente.post("/openfinance/connect-token")
        assert resposta.status_code == 502
        assert "Pluggy" in resposta.json()["detail"]
