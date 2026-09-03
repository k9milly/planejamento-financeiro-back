"""Ponto de entrada da API.

Rodar em desenvolvimento:
    uvicorn app.main:app --reload

A documentação interativa fica em http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.deps import usuario_atual
from app.routers import (
    alertas,
    anos,
    caixinhas,
    auth,
    categorias,
    contas,
    faturas,
    gastos_fixos,
    importacao,
    lancamentos,
    metas_poupanca,
    preferencias,
    regras,
    wishlist,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """A aplicação não cria nem altera tabelas ao subir.

    Antes ela chamava `create_all()`, o que era conveniente localmente e
    perigoso em produção: `create_all` cria tabelas que faltam mas ignora
    colunas novas, então um deploy com o schema desatualizado subiria
    normalmente e só quebraria na primeira consulta. O schema é responsabilidade
    do `alembic upgrade head`, rodado antes de iniciar.
    """
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

# --------------------------------------------------------------------------- #
# Erros: um formato só para a API inteira (ADR-01)
#
# Todo erro — de negócio, de validação ou inesperado — responde
# `{"detail": "frase em português"}`. Sem isto, quem consome precisa de três
# caminhos diferentes: string em `HTTPException`, lista de objetos em inglês
# no 422 do Pydantic, e um 500 sem corpo previsível.
# --------------------------------------------------------------------------- #


# Registrado ANTES do CORS de propósito: o middleware adicionado por último é o
# mais externo, então este fica por dentro e a resposta de erro que ele monta
# ainda passa pelo CORS na volta.
#
# O ADR-01 previa `@app.exception_handler(Exception)` para este caso. Não
# funciona sozinho: esse handler roda no `ServerErrorMiddleware` do Starlette,
# que fica acima de todos os middlewares da aplicação — a resposta 500 sairia
# sem os cabeçalhos de CORS, e o navegador esconderia a mensagem atrás de um
# erro de CORS genérico, justamente quando ela mais importa. Coberto por
# `tests/test_erros.py::test_500_chega_ao_navegador_com_cabecalho_cors`.
@app.middleware("http")
async def erro_inesperado(request: Request, call_next):
    """Rede de segurança: bug ou falha de banco vira 500 com a mesma forma.

    A causa real vai para o log do servidor, não para a resposta — um traceback
    na tela contaria a estrutura interna da aplicação a quem estiver olhando.
    """
    try:
        return await call_next(request)
    except Exception:
        logging.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno. Tente novamente em instantes."},
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
def _sem_prefixo_do_pydantic(mensagem: str) -> str:
    """O Pydantic prefixa o que vem de `model_validator` com "Value error, ".

    As regras de negócio já escrevem a frase pronta para exibição, então o
    prefixo só vaza vocabulário de biblioteca para a tela. Aplicado tanto ao
    `detail` quanto a cada item de `campos` — quem usa a lista para destacar
    o campo errado mostra a mesma frase de quem lê só o `detail`.
    """
    return mensagem.removeprefix("Value error, ")


@app.exception_handler(RequestValidationError)
async def erro_validacao(request: Request, exc: RequestValidationError):
    """Achata o 422 do Pydantic para a mesma forma dos erros de negócio.

    `campos` sobra para o formulário destacar o campo específico; quem só quer
    mostrar um aviso lê `detail` e ignora o resto.
    """
    erros = exc.errors()
    primeiro = erros[0] if erros else {}
    mensagem = _sem_prefixo_do_pydantic(primeiro.get("msg", "Dados inválidos."))

    return JSONResponse(
        status_code=422,
        content={
            "detail": mensagem,
            "campos": [
                {
                    # `loc[0]` é a origem ("body", "query"…), que não interessa
                    # a quem preenche o formulário. Vazio quando o erro é do
                    # modelo inteiro (regra de coerência entre campos), não de
                    # um campo só.
                    "campo": ".".join(str(parte) for parte in erro["loc"][1:]),
                    "mensagem": _sem_prefixo_do_pydantic(erro["msg"]),
                }
                for erro in erros
            ],
        },
    )


app.include_router(auth.router)

# Toda rota de dados exige sessão. Aplicado no registro do router, e não em
# cada função, para que uma rota nova nasça protegida — esquecer o decorador em
# um endpoint seria expor dados financeiros sem ninguém notar.
protegido = [Depends(usuario_atual)]

app.include_router(anos.router, dependencies=protegido)
app.include_router(contas.router, dependencies=protegido)
app.include_router(caixinhas.router, dependencies=protegido)
app.include_router(categorias.router, dependencies=protegido)
app.include_router(lancamentos.router, dependencies=protegido)
app.include_router(gastos_fixos.router, dependencies=protegido)
app.include_router(faturas.router, dependencies=protegido)
app.include_router(wishlist.router, dependencies=protegido)
app.include_router(regras.router, dependencies=protegido)
app.include_router(importacao.router, dependencies=protegido)
app.include_router(preferencias.router, dependencies=protegido)
app.include_router(metas_poupanca.router, dependencies=protegido)
app.include_router(alertas.router, dependencies=protegido)


@app.get("/saude", tags=["infra"], summary="Verificação de saúde")
def saude() -> dict[str, str]:
    return {"status": "ok"}
