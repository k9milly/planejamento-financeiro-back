"""Ponto de entrada da API.

Rodar em desenvolvimento:
    uvicorn app.main:app --reload

A documentação interativa fica em http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import criar_tabelas
from fastapi import Depends

from app.deps import usuario_atual
from app.routers import (
    anos,
    auth,
    categorias,
    gastos_fixos,
    importacao,
    lancamentos,
    regras,
    wishlist,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    criar_tabelas()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "API da planilha inteligente de controle financeiro pessoal. "
        "Organiza entradas, saídas e reserva em 12 páginas mensais por ano."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

# Toda rota de dados exige sessão. Aplicado no registro do router, e não em
# cada função, para que uma rota nova nasça protegida — esquecer o decorador em
# um endpoint seria expor dados financeiros sem ninguém notar.
protegido = [Depends(usuario_atual)]

app.include_router(anos.router, dependencies=protegido)
app.include_router(categorias.router, dependencies=protegido)
app.include_router(lancamentos.router, dependencies=protegido)
app.include_router(gastos_fixos.router, dependencies=protegido)
app.include_router(wishlist.router, dependencies=protegido)
app.include_router(regras.router, dependencies=protegido)
app.include_router(importacao.router, dependencies=protegido)


@app.get("/saude", tags=["infra"], summary="Verificação de saúde")
def saude() -> dict[str, str]:
    return {"status": "ok"}
