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
    # As duas portas cobrem os dois frontends que existem hoje em
    # desenvolvimento: 5173 é o Vite do frontend embutido neste repositório;
    # 8080 é o do `planejamento-financeiro-front`, que roda por um plugin da
    # Lovable e fixa essa porta (ver ADR-03 — o valor foi conferido rodando
    # `npm run dev` lá, não assumido).
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
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


settings = Settings()
