"""Open finance via Pluggy — por enquanto, só a porta de entrada.

Esta rota entrega ao frontend um **connect token**: um segredo de curta
duração que abre o widget da Pluggy no navegador, e nada mais. O `clientId` e
o `clientSecret` da aplicação ficam só no servidor — é a razão de a rota
existir, em vez de o frontend falar direto com a Pluggy.

## O que ainda não existe

Conectar o banco é o primeiro de vários passos. Depois do widget, a Pluggy
cria um *item* (a conexão com aquele banco) e passa a avisar por webhook
quando há transação nova. Nada disso está implementado: não há tabela de
item, nem webhook, nem importação de lançamento vindo daí.

Quando existir, o caminho natural é **desaguar no fluxo de importação que já
existe** (ADR-08 e ADR-12) em vez de um paralelo: a prévia, a deduplicação
por identificador, a sugestão de categoria e a confirmação em duas etapas já
estão escritas e testadas para OFX, CSV, XLSX e PDF. Uma transação da Pluggy
é mais uma origem de `TransacaoExtrato`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.deps import usuario_atual
from app.models import Usuario
from app.services.pluggy import (
    PluggyIndisponivel,
    PluggyNaoConfigurada,
    criar_connect_token,
)

router = APIRouter(prefix="/openfinance", tags=["open finance"])


class ConnectTokenOut(BaseModel):
    access_token: str


@router.post(
    "/connect-token",
    response_model=ConnectTokenOut,
    summary="Token para o navegador abrir o Pluggy Connect",
)
def connect_token(usuario: Usuario = Depends(usuario_atual)) -> ConnectTokenOut:
    """Exige sessão: quem não está logado não pede token de conexão bancária.

    ## De quem é a conexão

    O identificador mandado à Pluggy é o do **espaço**, não o da pessoa. É a
    decisão coerente com o ADR-15: dado financeiro pertence ao espaço, e um
    casal que divide o controle divide também a conta do banco conectada. Se
    fosse por usuário, a conexão sumiria da tela do outro membro e cada um
    teria de conectar o mesmo banco de novo.

    Fica registrado por ser uma decisão de privacidade, não um detalhe: é um
    campo só para trocar, mas muda quem enxerga o quê.

    Quem ainda não escolheu espaço recebe 409 — sem espaço não há onde o
    dinheiro entrar depois, e deixar conectar aqui adiaria o erro para um
    ponto bem pior.
    """
    if usuario.espaco_atual_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Escolha um espaço antes de conectar um banco.",
        )

    try:
        token = criar_connect_token(f"espaco-{usuario.espaco_atual_id}")
    except PluggyNaoConfigurada as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(erro)
        ) from erro
    except PluggyIndisponivel as erro:
        # 502 e não 500: o defeito é de quem respondeu lá fora, e a distinção
        # importa para quem for ler o log depois.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(erro)
        ) from erro

    return ConnectTokenOut(access_token=token)
