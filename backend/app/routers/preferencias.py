"""Preferências de exibição. Nenhuma pertence a um ano.

Duas coisas diferentes moram aqui, com donos diferentes de propósito:

- **cores da forma de pagamento**: globais. As quatro formas são fixas para o
  app inteiro, e a cor escolhida vale em qualquer aparelho.
- **layout do painel**: por usuário. A disposição da tela é de quem a arrumou.

Ambas ficam no banco — e não no navegador — porque o app é usado tanto no
celular quanto no PC, e uma preferência salva só em `localStorage` não
apareceria igual nos dois.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import usuario_atual
from app.models import CorFormaPagamento, FormaPagamento, Usuario
from app.schemas import (
    CorFormaPagamentoDefinir,
    CorFormaPagamentoOut,
    LayoutDashboardDefinir,
    LayoutDashboardOut,
)

router = APIRouter(prefix="/preferencias", tags=["preferencias"])

# Usada quando a usuária ainda não escolheu uma cor para a forma de pagamento.
CORES_PADRAO: dict[FormaPagamento, str] = {
    FormaPagamento.DINHEIRO: "#22c55e",
    FormaPagamento.DEBITO: "#0ea5e9",
    FormaPagamento.PIX: "#14b8a6",
    FormaPagamento.CREDITO: "#f97316",
}


@router.get(
    "/cores-forma-pagamento",
    response_model=list[CorFormaPagamentoOut],
    summary="Lista a cor de cada forma de pagamento",
)
def listar(db: Session = Depends(get_db)) -> list[CorFormaPagamentoOut]:
    salvas = {c.forma_pagamento: c.cor for c in db.query(CorFormaPagamento).all()}
    return [
        CorFormaPagamentoOut(forma_pagamento=forma, cor=salvas.get(forma, padrao))
        for forma, padrao in CORES_PADRAO.items()
    ]


@router.put(
    "/cores-forma-pagamento/{forma_pagamento}",
    response_model=CorFormaPagamentoOut,
    summary="Define a cor de uma forma de pagamento",
)
def definir(
    forma_pagamento: FormaPagamento,
    dados: CorFormaPagamentoDefinir,
    db: Session = Depends(get_db),
) -> CorFormaPagamento:
    registro = db.get(CorFormaPagamento, forma_pagamento)
    if registro is None:
        registro = CorFormaPagamento(forma_pagamento=forma_pagamento, cor=dados.cor)
        db.add(registro)
    else:
        registro.cor = dados.cor
    db.commit()
    db.refresh(registro)
    return registro


@router.get(
    "/layout-dashboard",
    response_model=LayoutDashboardOut,
    summary="Layout do painel salvo por este usuário",
)
def obter_layout(usuario: Usuario = Depends(usuario_atual)) -> LayoutDashboardOut:
    """`layout` vem `null` enquanto o usuário nunca tiver arrumado o painel —
    é o sinal para o frontend usar a disposição padrão dele."""
    return LayoutDashboardOut(layout=usuario.layout_dashboard)


@router.put(
    "/layout-dashboard",
    response_model=LayoutDashboardOut,
    summary="Salva o layout do painel deste usuário",
)
def definir_layout(
    dados: LayoutDashboardDefinir,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> LayoutDashboardOut:
    """Responde com o que ficou salvo, em vez de `204`.

    O contrato deixava a escolha em aberto; devolver o valor mantém o mesmo
    formato do `GET`, então o frontend pode usar a resposta do `PUT`
    diretamente como novo estado, sem uma segunda chamada para reler.
    """
    usuario.layout_dashboard = dados.layout
    db.commit()
    return LayoutDashboardOut(layout=usuario.layout_dashboard)
