"""Configuração da aplicação, lida de variáveis de ambiente ou de um .env."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Planejamento Financeiro"

    # O banco fica ao lado do código por padrão; é um arquivo só, fácil de
    # copiar ou fazer backup manualmente. Em produção vem do ambiente, com
    # `postgresql+psycopg://...`.
    database_url: str = f"sqlite:///{RAIZ / 'dados.db'}"

    # Origens liberadas no CORS: quais sites podem chamar esta API pelo
    # navegador. O padrão cobre o Vite local. Em produção, defina
    # CORS_ORIGINS com o(s) endereço(s) do frontend, separados por vírgula
    # se houver mais de um — sem colchetes, sem aspas:
    #   CORS_ORIGINS=https://planejamento.netlify.app
    # `NoDecode` desliga a decodificação JSON automática do pydantic-settings
    # para este campo: por padrão, uma lista é sempre lida como JSON, e um
    # terminal (PowerShell, principalmente) troca ou perde aspas com
    # facilidade ao repassar `["..."]` — foi exatamente isso que derrubou a
    # aplicação em produção num crash-loop, sem nenhuma mensagem visível para
    # quem só olhava o navegador. O parser abaixo aceita tanto o formato
    # simples (recomendado) quanto JSON, para não quebrar quem já configurou
    # do jeito antigo.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _ler_cors_origins(cls, valor: object) -> object:
        if not isinstance(valor, str):
            return valor
        texto = valor.strip()
        if not texto:
            return []
        if texto.startswith("["):
            return json.loads(texto)
        return [origem.strip() for origem in texto.split(",") if origem.strip()]

    # Chave que assina os tokens de sessão. O padrão é aleatório a cada
    # inicialização: em desenvolvimento isso só derruba a sessão ao reiniciar,
    # mas em produção **precisa** vir do ambiente — sem isso, todo deploy
    # desloga todo mundo, e réplicas diferentes não reconheceriam os tokens
    # umas das outras.
    secret_key: str = secrets.token_urlsafe(32)

    # Sessão longa de propósito: é um app pessoal de uso diário, e exigir
    # login toda hora no celular faria a pessoa desistir de usar.
    token_expira_horas: int = 24 * 30

    # Lançamento rápido por mensagem do Telegram. As três variáveis vêm
    # juntas: sem qualquer uma delas, a rota do webhook responde 404 e o
    # recurso fica desativado — não há um "meio ligado".
    telegram_bot_token: str = ""

    # Verificado contra o cabeçalho X-Telegram-Bot-Api-Secret-Token, que o
    # Telegram reenvia em toda chamada ao webhook depois de configurado via
    # `setWebhook`. Sem isso, qualquer pessoa que descobrisse a URL do webhook
    # conseguiria forjar lançamentos na sua conta.
    telegram_webhook_secret: str = ""

    # Só mensagens vindas deste chat viram lançamento; qualquer outro
    # remetente é ignorado em silêncio — nem confirma, nem nega, para não
    # revelar que o bot existe a quem não deveria falar com ele.
    telegram_chat_id: int = 0


settings = Settings()
