"""Metas de poupança: quanto se quer guardar, por mês ou até uma data (ADR-06).

O progresso nunca é guardado em coluna — vem do mesmo cálculo que alimenta
`GET /anos/{ano}/resumo`. Duas contas do mesmo número acabariam discordando.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ano, Lancamento, MetaPoupanca, TipoMetaPoupanca
from app.routers.anos import totais_do_ano
from app.services.calculos import variacao_do_guardado
from app.schemas import (
    MetaPoupancaCriar,
    MetaPoupancaOut,
    MetasAtivasOut,
    ProgressoMetaMensalOut,
    ProgressoMetaPrazoOut,
)

router = APIRouter(prefix="/metas-poupanca", tags=["metas de poupança"])

ZERO = Decimal("0.00")


@router.get("", response_model=list[MetaPoupancaOut], summary="Lista as metas")
def listar(
    incluir_inativas: bool = False, db: Session = Depends(get_db)
) -> list[MetaPoupanca]:
    """Mesma convenção de `/categorias`: por padrão só o que está valendo.

    As inativas são o histórico do que já se pretendeu poupar — some do
    progresso, mas não do banco.
    """
    consulta = db.query(MetaPoupanca)
    if not incluir_inativas:
        consulta = consulta.filter(MetaPoupanca.ativa.is_(True))
    return consulta.order_by(MetaPoupanca.criada_em.desc()).all()


@router.post(
    "",
    response_model=MetaPoupancaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma meta (e aposenta a anterior do mesmo tipo)",
)
def criar(dados: MetaPoupancaCriar, db: Session = Depends(get_db)) -> MetaPoupanca:
    """No máximo uma meta ativa por tipo.

    Criar substitui a anterior em vez de recusar: quem define uma meta nova
    está dizendo que a antiga não vale mais, e obrigar a desativar antes seria
    um passo a mais para dizer a mesma coisa. A antiga vira `ativa=False`, não
    é apagada.
    """
    anterior = (
        db.query(MetaPoupanca)
        .filter(MetaPoupanca.tipo == dados.tipo, MetaPoupanca.ativa.is_(True))
        .all()
    )
    for meta in anterior:
        meta.ativa = False

    meta = MetaPoupanca(**dados.model_dump())
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


@router.get(
    "/ativas",
    response_model=MetasAtivasOut,
    summary="As metas em vigor, com o progresso já calculado",
)
def ativas(db: Session = Depends(get_db)) -> MetasAtivasOut:
    """Progresso medido contra o ano corrente.

    Uma meta não pertence a um ano — mas "quanto já guardei" só faz sentido
    dentro de um. Se o ano de hoje ainda não foi criado no sistema, o
    progresso é zero em vez de erro: a meta existe, só não há movimento contra
    o que medi-la.
    """
    hoje = date.today()
    ano_ref = db.query(Ano).filter(Ano.ano == hoje.year).one_or_none()
    meses = totais_do_ano(ano_ref, db) if ano_ref else None

    return MetasAtivasOut(
        mensal=_progresso_mensal(_ativa(TipoMetaPoupanca.MENSAL, db), meses, hoje),
        prazo=_progresso_prazo(_ativa(TipoMetaPoupanca.PRAZO, db), hoje, db),
    )


@router.delete(
    "/{meta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativa uma meta",
)
def desativar(meta_id: int, db: Session = Depends(get_db)) -> None:
    """Nunca apaga de verdade: a meta vira histórico, como acontece ao ser
    substituída por outra do mesmo tipo."""
    meta = db.get(MetaPoupanca, meta_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meta {meta_id} não existe.",
        )
    meta.ativa = False
    db.commit()


def _ativa(tipo: TipoMetaPoupanca, db: Session) -> MetaPoupanca | None:
    return (
        db.query(MetaPoupanca)
        .filter(MetaPoupanca.tipo == tipo, MetaPoupanca.ativa.is_(True))
        .order_by(MetaPoupanca.criada_em.desc())
        .first()
    )


def _percentual(guardado: Decimal, alvo: Decimal) -> float:
    """Sem teto em 100: bater 130% do alvo é informação, não erro.

    Piso em 0 porque um mês em que se retirou mais do que se guardou daria
    percentual negativo, o que confundiria uma barra de progresso.
    """
    if alvo <= 0:
        return 0.0
    return max(0.0, round(float(guardado / alvo) * 100, 2))


def _progresso_mensal(
    meta: MetaPoupanca | None, meses, hoje: date
) -> ProgressoMetaMensalOut | None:
    if meta is None:
        return None
    guardado = meses[hoje.month - 1].guardado_no_mes if meses else ZERO
    return ProgressoMetaMensalOut(
        id=meta.id,
        valor_alvo=meta.valor_alvo,
        guardado_no_mes=guardado,
        percentual=_percentual(guardado, meta.valor_alvo),
    )


def _progresso_prazo(
    meta: MetaPoupanca | None, hoje: date, db: Session
) -> ProgressoMetaPrazoOut | None:
    """Conta só o que foi guardado **desde que a meta foi criada**.

    Usar o saldo da reserva aqui daria a uma meta recém-criada o progresso de
    tudo o que já estava guardado antes — quem decide hoje juntar R$ 6.000
    veria "217% concluído" antes de guardar o primeiro real.

    Por isso não passa pelos totais mensais: o período de uma meta começa num
    dia qualquer, não no primeiro do mês, e atravessa anos. A comparação é por
    data do lançamento — `Lancamento` não guarda hora, então tudo o que foi
    lançado no dia em que a meta nasceu conta para ela.
    """
    if meta is None:
        return None

    desde = meta.criada_em.date()
    lancamentos = (
        db.query(Lancamento)
        .filter(Lancamento.data >= desde, Lancamento.data <= hoje)
        .all()
    )
    guardado = variacao_do_guardado(lancamentos)

    return ProgressoMetaPrazoOut(
        id=meta.id,
        valor_alvo=meta.valor_alvo,
        data_alvo=meta.data_alvo,
        guardado_acumulado=guardado,
        percentual=_percentual(guardado, meta.valor_alvo),
        dias_restantes=(meta.data_alvo - hoje).days,
    )
