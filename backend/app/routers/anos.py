"""Endpoints de anos: criação, arquivamento e os resumos que alimentam a tela."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import MESES_PT, obter_ano
from app.models import Ano, Lancamento
from app.schemas import (
    AnoCriar,
    AnoOut,
    GastoCategoriaOut,
    ResumoAnoOut,
    ResumoMesOut,
)
from app.services.calculos import calcular_ano

router = APIRouter(prefix="/anos", tags=["anos"])


@router.get("", response_model=list[AnoOut], summary="Lista todos os anos")
def listar_anos(db: Session = Depends(get_db)) -> list[Ano]:
    """Inclui os arquivados — é essa lista que monta a 'pasta' de anos anteriores."""
    return db.query(Ano).order_by(Ano.ano.desc()).all()


@router.post(
    "", response_model=AnoOut, status_code=status.HTTP_201_CREATED,
    summary="Cria um ano",
)
def criar_ano(dados: AnoCriar, db: Session = Depends(get_db)) -> Ano:
    if db.query(Ano).filter(Ano.ano == dados.ano).one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O ano {dados.ano} já existe.",
        )
    registro = Ano(**dados.model_dump())
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


@router.post(
    "/{ano}/arquivar",
    response_model=AnoOut,
    summary="Arquiva o ano e gera o seguinte",
)
def arquivar_ano(
    ano_ref: Ano = Depends(obter_ano), db: Session = Depends(get_db)
) -> Ano:
    """Fecha o ano e prepara o próximo com os saldos de fechamento como abertura.

    Se o ano seguinte ainda não existe, é criado. Se já existe **e ainda não
    tem lançamentos**, seus saldos de abertura são atualizados: eles eram
    placeholders zerados de um ano criado antecipadamente para planejamento, e
    mantê-los produziria totais errados. Um ano seguinte que já tenha
    lançamentos é preservado intacto.
    """
    if ano_ref.arquivado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O ano {ano_ref.ano} já está arquivado.",
        )

    meses = _calcular(ano_ref, db)
    fechamento = meses[-1]

    ano_ref.arquivado = True
    ano_ref.arquivado_em = datetime.now()

    proximo = db.query(Ano).filter(Ano.ano == ano_ref.ano + 1).one_or_none()
    if proximo is None:
        db.add(
            Ano(
                ano=ano_ref.ano + 1,
                saldo_inicial_conta=fechamento.saldo,
                saldo_inicial_guardado=fechamento.guardado_acumulado,
            )
        )
    elif not db.query(Lancamento).filter(Lancamento.ano_id == proximo.id).count():
        proximo.saldo_inicial_conta = fechamento.saldo
        proximo.saldo_inicial_guardado = fechamento.guardado_acumulado

    db.commit()
    db.refresh(ano_ref)
    return ano_ref


@router.post(
    "/{ano}/desarquivar", response_model=AnoOut, summary="Reabre um ano arquivado"
)
def desarquivar_ano(
    ano_ref: Ano = Depends(obter_ano), db: Session = Depends(get_db)
) -> Ano:
    ano_ref.arquivado = False
    ano_ref.arquivado_em = None
    db.commit()
    db.refresh(ano_ref)
    return ano_ref


@router.get(
    "/{ano}/resumo",
    response_model=ResumoAnoOut,
    summary="Totais do ano e de cada um dos 12 meses",
)
def resumo_do_ano(
    ano_ref: Ano = Depends(obter_ano), db: Session = Depends(get_db)
) -> ResumoAnoOut:
    """Uma única chamada devolve tudo que as 12 páginas precisam."""
    meses = _calcular(ano_ref, db)

    resumos: list[ResumoMesOut] = []
    for t in meses:
        total_gastos = sum(t.gastos_por_categoria.values(), Decimal("0.00"))
        resumos.append(
            ResumoMesOut(
                mes=t.mes,
                nome_mes=MESES_PT[t.mes - 1],
                entradas=t.entradas,
                saidas=t.saidas,
                guardado_no_mes=t.guardado_no_mes,
                saldo=t.saldo,
                saldo_inicial=t.saldo_inicial,
                guardado_acumulado=t.guardado_acumulado,
                rendimento_conta=t.rendimento_conta,
                rendimento_guardado=t.rendimento_guardado,
                gastos_por_categoria=[
                    GastoCategoriaOut(
                        categoria=nome,
                        total=valor,
                        # Percentual dentro do mês; com 0 gastos evitamos divisão por zero.
                        percentual=(
                            float(valor / total_gastos * 100) if total_gastos else 0.0
                        ),
                    )
                    for nome, valor in t.gastos_por_categoria.items()
                ],
            )
        )

    return ResumoAnoOut(
        ano=ano_ref.ano,
        arquivado=ano_ref.arquivado,
        saldo_inicial_conta=Decimal(str(ano_ref.saldo_inicial_conta)),
        saldo_inicial_guardado=Decimal(str(ano_ref.saldo_inicial_guardado)),
        total_guardado=meses[-1].guardado_acumulado,
        saldo_final=meses[-1].saldo,
        total_entradas=sum((t.entradas for t in meses), Decimal("0.00")),
        total_saidas=sum((t.saidas for t in meses), Decimal("0.00")),
        meses=resumos,
    )


def _calcular(ano_ref: Ano, db: Session):
    """Carrega os lançamentos do ano (com categoria) e roda o cálculo."""
    lancamentos = (
        db.query(Lancamento)
        .options(joinedload(Lancamento.categoria))
        .filter(Lancamento.ano_id == ano_ref.id)
        .all()
    )
    return calcular_ano(
        lancamentos,
        Decimal(str(ano_ref.saldo_inicial_conta)),
        Decimal(str(ano_ref.saldo_inicial_guardado)),
    )
