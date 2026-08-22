"""Preferências de exibição globais (cores da forma de pagamento).

Não têm dono nem ano: as quatro formas de pagamento são fixas para o app
inteiro, e a cor escolhida vale em qualquer aparelho — ver `CorFormaPagamento`
em `app/models.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CorFormaPagamento, FormaPagamento
from app.schemas import CorFormaPagamentoDefinir, CorFormaPagamentoOut

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
