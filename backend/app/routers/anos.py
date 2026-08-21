"""Endpoints de anos: criação, arquivamento e os resumos que alimentam a tela."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import MESES_PT, obter_ano
from app.models import Ano, Conta, Lancamento, SaldoInicial
from app.schemas import (
    AnoCriar,
    AnoOut,
    CarteirasContaOut,
    GastoCategoriaOut,
    ResumoAnoOut,
    ResumoMesOut,
    SaldoInicialDefinir,
)
from app.services.calculos import Carteiras, calcular_ano

router = APIRouter(prefix="/anos", tags=["anos"])

ZERO = Decimal("0.00")


@router.get("", response_model=list[AnoOut], summary="Lista todos os anos")
def listar_anos(db: Session = Depends(get_db)) -> list[Ano]:
    """Inclui os arquivados — é essa lista que monta a 'pasta' de anos anteriores."""
    return (
        db.query(Ano)
        .options(joinedload(Ano.saldos_iniciais))
        .order_by(Ano.ano.desc())
        .all()
    )


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

    registro = Ano(ano=dados.ano)
    db.add(registro)
    db.flush()

    _definir_saldos(registro, dados.saldos_iniciais, db)

    db.commit()
    db.refresh(registro)
    return registro


@router.put(
    "/{ano}/saldos-iniciais",
    response_model=AnoOut,
    summary="Ajusta os saldos de abertura do ano",
)
def definir_saldos_iniciais(
    saldos: list[SaldoInicialDefinir],
    ano_ref: Ano = Depends(obter_ano),
    db: Session = Depends(get_db),
) -> Ano:
    """Substitui as aberturas informadas. Contas omitidas ficam como estavam."""
    if ano_ref.arquivado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O ano {ano_ref.ano} está arquivado e é somente leitura.",
        )
    _definir_saldos(ano_ref, saldos, db)
    db.commit()
    db.refresh(ano_ref)
    return ano_ref


@router.post(
    "/{ano}/arquivar",
    response_model=AnoOut,
    summary="Arquiva o ano e prepara o seguinte",
)
def arquivar_ano(
    ano_ref: Ano = Depends(obter_ano), db: Session = Depends(get_db)
) -> Ano:
    """Fecha o ano e leva os saldos de fechamento de cada conta para o seguinte.

    Se o ano seguinte ainda não existe, é criado. Se existe **e ainda não tem
    lançamentos**, suas aberturas são atualizadas: eram placeholders de um ano
    criado antecipadamente para planejamento. Um ano seguinte que já tenha
    lançamentos é preservado intacto.
    """
    if ano_ref.arquivado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O ano {ano_ref.ano} já está arquivado.",
        )

    meses = _calcular(ano_ref, db)
    # Inclui cartões: a dívida em aberto também precisa encadear para o ano
    # seguinte, do mesmo jeito que o saldo de uma conta corrente.
    fechamento = {**meses[-1].por_conta, **meses[-1].por_cartao}

    ano_ref.arquivado = True
    ano_ref.arquivado_em = datetime.now()

    proximo = db.query(Ano).filter(Ano.ano == ano_ref.ano + 1).one_or_none()

    if proximo is None:
        proximo = Ano(ano=ano_ref.ano + 1)
        db.add(proximo)
        db.flush()
    elif db.query(Lancamento).filter(Lancamento.ano_id == proximo.id).count():
        db.commit()
        db.refresh(ano_ref)
        return ano_ref

    _definir_saldos(
        proximo,
        [
            SaldoInicialDefinir(
                conta_id=conta_id, saldo=c.saldo, guardado=c.guardado
            )
            for conta_id, c in fechamento.items()
        ],
        db,
    )

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
    contas = {c.id: c for c in db.query(Conta).order_by(Conta.ordem, Conta.nome)}

    def por_conta(carteiras: dict[int, Carteiras]) -> list[CarteirasContaOut]:
        return [
            CarteirasContaOut(
                conta_id=conta_id,
                nome=contas[conta_id].nome if conta_id in contas else "?",
                cor=contas[conta_id].cor if conta_id in contas else "#8d7799",
                saldo=c.saldo,
                guardado=c.guardado,
            )
            # Ordena pela ordem definida na conta, não pelo id.
            for conta_id, c in sorted(
                carteiras.items(),
                key=lambda kv: (
                    contas[kv[0]].ordem if kv[0] in contas else 999,
                    contas[kv[0]].nome if kv[0] in contas else "",
                ),
            )
        ]

    resumos: list[ResumoMesOut] = []
    for t in meses:
        total_gastos = sum(t.gastos_por_categoria.values(), ZERO)
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
                rendimentos=t.rendimentos,
                perdas=t.perdas,
                transferido=t.transferido,
                por_conta=por_conta(t.por_conta),
                por_cartao=por_conta(t.por_cartao),
                gastos_por_categoria=[
                    GastoCategoriaOut(
                        categoria=nome,
                        total=valor,
                        # Percentual dentro do mês; com 0 gastos evitamos
                        # divisão por zero.
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
        total_guardado=meses[-1].guardado_acumulado,
        saldo_final=meses[-1].saldo,
        total_entradas=sum((t.entradas for t in meses), ZERO),
        total_saidas=sum((t.saidas for t in meses), ZERO),
        por_conta=por_conta(meses[-1].por_conta),
        por_cartao=por_conta(meses[-1].por_cartao),
        meses=resumos,
    )


def _definir_saldos(
    ano_ref: Ano, saldos: list[SaldoInicialDefinir], db: Session
) -> None:
    """Grava as aberturas informadas, criando ou atualizando cada linha."""
    for item in saldos:
        if db.get(Conta, item.conta_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Conta {item.conta_id} não existe.",
            )

        registro = (
            db.query(SaldoInicial)
            .filter(
                SaldoInicial.ano_id == ano_ref.id,
                SaldoInicial.conta_id == item.conta_id,
            )
            .one_or_none()
        )
        if registro is None:
            db.add(
                SaldoInicial(
                    ano_id=ano_ref.id,
                    conta_id=item.conta_id,
                    saldo=item.saldo,
                    guardado=item.guardado,
                )
            )
        else:
            registro.saldo = item.saldo
            registro.guardado = item.guardado


def aberturas_do_ano(ano_ref: Ano, db: Session) -> dict[int, Carteiras]:
    """Carteiras de cada conta no começo do ano.

    Contas sem linha de abertura entram zeradas, para aparecerem no resumo
    mesmo antes do primeiro lançamento.
    """
    aberturas = {
        s.conta_id: Carteiras(
            saldo=Decimal(str(s.saldo)), guardado=Decimal(str(s.guardado))
        )
        for s in db.query(SaldoInicial).filter(SaldoInicial.ano_id == ano_ref.id)
    }
    for conta in db.query(Conta).filter(Conta.ativa.is_(True)):
        aberturas.setdefault(conta.id, Carteiras())
    return aberturas


def _calcular(ano_ref: Ano, db: Session):
    """Carrega os lançamentos do ano (com categoria) e roda o cálculo."""
    lancamentos = (
        db.query(Lancamento)
        .options(joinedload(Lancamento.categoria))
        .filter(Lancamento.ano_id == ano_ref.id)
        .all()
    )
    # Precisa de todas as contas, não só as ativas: um lançamento antigo pode
    # apontar para uma conta já desativada, e ela precisa continuar sendo
    # reconhecida como corrente ou cartão para o cálculo separar certo.
    tipos_conta = {c.id: c.tipo for c in db.query(Conta)}
    return calcular_ano(lancamentos, aberturas_do_ano(ano_ref, db), tipos_conta)
