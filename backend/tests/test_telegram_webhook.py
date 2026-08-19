"""Testes do webhook de lançamento rápido por Telegram.

`_responder` (o envio de volta ao Telegram) é sempre substituído por um dublê
que só grava o que foi chamado — nenhum teste bate na internet de verdade.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.routers import telegram as telegram_router

CHAT_AUTORIZADO = 123456789
SEGREDO = "segredo-de-teste"


@pytest.fixture(autouse=True)
def _configurar_telegram(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "token-fake")
    monkeypatch.setattr(settings, "telegram_webhook_secret", SEGREDO)
    monkeypatch.setattr(settings, "telegram_chat_id", CHAT_AUTORIZADO)


@pytest.fixture()
def respostas_enviadas(monkeypatch):
    """Substitui o envio real ao Telegram por uma lista que registra o que
    seria mandado, e devolve essa lista para o teste inspecionar."""
    enviadas: list[tuple[int, str]] = []

    async def _fake(chat_id: int, texto: str) -> None:
        enviadas.append((chat_id, texto))

    monkeypatch.setattr(telegram_router, "_responder", _fake)
    return enviadas


def _update(texto: str, chat_id: int = CHAT_AUTORIZADO, timestamp: int = 1_755_000_000):
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": timestamp,
            "chat": {"id": chat_id},
            "text": texto,
        },
    }


def _post(cliente_sem_login, corpo, segredo=SEGREDO):
    headers = {}
    if segredo is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = segredo
    return cliente_sem_login.post("/webhooks/telegram", json=corpo, headers=headers)


class TestSeguranca:
    def test_sem_segredo_configurado_a_rota_nao_existe(
        self, cliente_sem_login, monkeypatch
    ):
        monkeypatch.setattr(settings, "telegram_webhook_secret", "")
        resposta = _post(cliente_sem_login, _update("15, brownie"), segredo=SEGREDO)
        assert resposta.status_code == 404

    def test_segredo_errado_e_recusado(self, cliente_sem_login):
        resposta = _post(cliente_sem_login, _update("15, brownie"), segredo="errado")
        assert resposta.status_code == 403

    def test_sem_cabecalho_de_segredo_e_recusado(self, cliente_sem_login):
        resposta = _post(cliente_sem_login, _update("15, brownie"), segredo=None)
        assert resposta.status_code == 403

    def test_chat_nao_autorizado_e_ignorado_em_silencio(
        self, cliente_sem_login, respostas_enviadas
    ):
        """Nem erro, nem confirmação — quem não é você não fica sabendo que
        o bot sequer processou a mensagem."""
        resposta = _post(cliente_sem_login, _update("15, brownie", chat_id=999))
        assert resposta.status_code == 200
        assert respostas_enviadas == []

    def test_atualizacao_sem_mensagem_de_texto_e_ignorada(self, cliente_sem_login):
        resposta = cliente_sem_login.post(
            "/webhooks/telegram",
            json={"update_id": 1, "edited_message": {}},
            headers={"X-Telegram-Bot-Api-Secret-Token": SEGREDO},
        )
        assert resposta.status_code == 200


class TestLancamentoPorMensagem:
    def test_cria_saida_com_a_data_do_envio(
        self, cliente, cliente_sem_login, respostas_enviadas, conta
    ):
        # `cliente` (autenticado) cria o ano 2025 pela API normal; a data de
        # timestamp abaixo cai em 2025.
        cliente.post("/anos", json={"ano": 2025})

        resposta = _post(
            cliente_sem_login,
            _update(
                "15 reais, brownie, mercado pago",
                timestamp=1_735_700_000,  # 31/12/2024 ~ ajustado abaixo
            ),
        )
        assert resposta.status_code == 200

        assert len(respostas_enviadas) == 1
        chat_id, texto = respostas_enviadas[0]
        assert chat_id == CHAT_AUTORIZADO
        assert "✅" in texto
        assert "brownie" in texto
        assert conta["nome"] in texto

        lancamentos = cliente.get(
            f"/anos/{_ano_do_timestamp(1_735_700_000)}/lancamentos"
        ).json()
        assert len(lancamentos) == 1
        assert lancamentos[0]["valor"] == "15.00"
        assert lancamentos[0]["descricao"] == "brownie"
        assert lancamentos[0]["tipo"] == "saida"
        assert lancamentos[0]["conta_id"] == conta["id"]

    def test_sugere_categoria_pela_mesma_regra_do_ofx(
        self, cliente, cliente_sem_login, respostas_enviadas, conta
    ):
        comida = cliente.post("/categorias", json={"nome": "Comida"}).json()
        cliente.post("/regras", json={"padrao": "brownie", "categoria_id": comida["id"]})
        cliente.post("/anos", json={"ano": 2025})

        _post(cliente_sem_login, _update("15, brownie", timestamp=1_735_700_000))

        lancamentos = cliente.get(
            f"/anos/{_ano_do_timestamp(1_735_700_000)}/lancamentos"
        ).json()
        assert lancamentos[0]["categoria"]["nome"] == "Comida"

    def test_ano_inexistente_responde_erro_sem_criar_lancamento(
        self, cliente_sem_login, respostas_enviadas
    ):
        _post(cliente_sem_login, _update("15, brownie", timestamp=1_735_700_000))
        assert len(respostas_enviadas) == 1
        assert "não existe" in respostas_enviadas[0][1]

    def test_mensagem_mal_formada_responde_erro_explicativo(
        self, cliente, cliente_sem_login, respostas_enviadas
    ):
        cliente.post("/anos", json={"ano": 2025})
        _post(
            cliente_sem_login,
            _update("brownie sem valor", timestamp=1_735_700_000),
        )
        assert "⚠️" in respostas_enviadas[0][1]
        assert cliente.get(f"/anos/{_ano_do_timestamp(1_735_700_000)}/lancamentos").json() == []

    def test_conta_nao_reconhecida_cai_na_padrao_com_aviso(
        self, cliente, cliente_sem_login, respostas_enviadas, conta
    ):
        cliente.post("/anos", json={"ano": 2025})
        _post(
            cliente_sem_login,
            _update("15, brownie, carteira", timestamp=1_735_700_000),
        )
        texto = respostas_enviadas[0][1]
        assert "não reconheci" in texto
        lancamentos = cliente.get(
            f"/anos/{_ano_do_timestamp(1_735_700_000)}/lancamentos"
        ).json()
        assert lancamentos[0]["conta_id"] == conta["id"]

    def test_ano_arquivado_recusa_lancamento(
        self, cliente, cliente_sem_login, respostas_enviadas
    ):
        cliente.post("/anos", json={"ano": 2025})
        cliente.post("/anos/2025/arquivar")

        _post(cliente_sem_login, _update("15, brownie", timestamp=1_735_700_000))
        assert "arquivado" in respostas_enviadas[0][1]


def _ano_do_timestamp(timestamp: int) -> int:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).year
