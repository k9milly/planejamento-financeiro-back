"""Configuração da aplicação, lida de variáveis de ambiente ou de um .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Planejamento Financeiro"

    # O banco fica ao lado do código por padrão; é um arquivo só, fácil de
    # copiar ou fazer backup manualmente.
    database_url: str = f"sqlite:///{RAIZ / 'dados.db'}"

    # Origens liberadas no CORS. Em produção, restringir ao domínio do frontend.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


settings = Settings()
