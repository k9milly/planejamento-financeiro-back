"""Saldo das caixinhas — derivado, nunca guardado (ADR-10).

Uma caixinha é um rótulo sobre uma parte do `guardado` de uma conta. O saldo
dela é `saldo_inicial` mais o efeito dos lançamentos que apontam para ela:

* os quatro tipos que mexem na reserva (`guardado`, `retirado`, e
  `rendimento`/`perda` com `destino=guardado`), reaproveitando a mesma regra
  que `calculos.variacao_do_guardado` já aplica ao guardado da conta — se as
  duas divergissem, a soma das caixinhas deixaria de bater com o total;
* as transferências entre caixinhas, que somam de um lado e subtraem do outro
  sem mexer no guardado da conta.

O que **sobra** do guardado da conta depois de descontar as caixinhas ativas é
o "guardado sem caixinha": o dinheiro que existia antes deste ADR, ou que
ainda não foi organizado. É contra ele que `saldo_inicial` é validado na
criação — senão uma caixinha nova inventaria dinheiro que a conta não tem.

**Nenhuma caixinha pode ficar com saldo negativo.** Como o saldo é derivado,
não basta checar a operação que a pessoa está fazendo: retirar mais do que a
caixinha tem, apagar o depósito que financiou uma retirada antiga, ou editar o
valor de um lançamento já gravado levam ao mesmo lugar por caminhos
diferentes. Por isso `garantir_nao_negativas` roda depois da mudança já estar
aplicada na sessão (no `flush`, antes do `commit`) e olha o resultado — que é
a única coisa que precisa fazer sentido, independente de como se chegou nele.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Ano, Caixinha, Lancamento, TipoLancamento
from app.services.calculos import variacao_do_guardado

ZERO = Decimal("0.00")


def _d(valor) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"))


def saldos(caixinhas: list[Caixinha], db: Session) -> dict[int, Decimal]:
    """Saldo atual de cada caixinha, em uma passada só.

    Recebe a lista pronta em vez de consultar por caixinha: a tela de
    Investimentos mostra todas de uma vez, e uma consulta por linha seria N+1.
    """
    if not caixinhas:
        return {}

    ids = {c.id for c in caixinhas}
    total = {c.id: _d(c.saldo_inicial) for c in caixinhas}

    lancamentos = (
        db.query(Lancamento)
        .filter(
            (Lancamento.caixinha_id.in_(ids))
            | (Lancamento.caixinha_destino_id.in_(ids))
        )
        .all()
    )

    # Movimento vindo dos tipos que mexem na reserva. A transferência entre
    # caixinhas não está entre eles — `variacao_do_guardado` a ignora, porque
    # ela não muda o guardado da conta —, então é somada logo abaixo.
    por_caixinha: dict[int, list[Lancamento]] = {c.id: [] for c in caixinhas}
    for lanc in lancamentos:
        if lanc.tipo is TipoLancamento.TRANSFERENCIA_CAIXINHA:
            valor = _d(lanc.valor)
            if lanc.caixinha_id in total:
                total[lanc.caixinha_id] -= valor
            if lanc.caixinha_destino_id in total:
                total[lanc.caixinha_destino_id] += valor
        elif lanc.caixinha_id in por_caixinha:
            por_caixinha[lanc.caixinha_id].append(lanc)

    for caixinha_id, do_grupo in por_caixinha.items():
        total[caixinha_id] += variacao_do_guardado(do_grupo)

    return total


def saldo(caixinha: Caixinha, db: Session) -> Decimal:
    return saldos([caixinha], db).get(caixinha.id, ZERO)


def ativas_da_conta(conta_id: int, db: Session) -> list[Caixinha]:
    return (
        db.query(Caixinha)
        .filter(Caixinha.conta_id == conta_id, Caixinha.ativa.is_(True))
        .order_by(Caixinha.criada_em, Caixinha.id)
        .all()
    )


def guardado_da_conta(conta_id: int, db: Session) -> Decimal:
    """Quanto a conta tem guardado hoje, pelo mesmo cálculo do resumo do ano.

    Usa o ano corrente porque é o que a tela mostra e onde a reserva atual
    vive. Ano ainda não criado no sistema devolve zero, em vez de erro — a
    conta existe, só não há movimento contra o que medi-la (mesma escolha que
    `GET /metas-poupanca/ativas` já faz).
    """
    from datetime import date

    from app.routers.anos import totais_do_ano

    ano_ref = db.query(Ano).filter(Ano.ano == date.today().year).one_or_none()
    if ano_ref is None:
        return ZERO

    fechamento = totais_do_ano(ano_ref, db)[-1]
    carteiras = fechamento.por_conta.get(conta_id)
    return carteiras.guardado if carteiras else ZERO


def garantir_nao_negativas(ids: set[int], db: Session, erro) -> None:
    """Recusa a operação se alguma das caixinhas terminar negativa.

    Chamar **depois** do `flush` e **antes** do `commit`: os saldos são
    calculados a partir do que está na sessão, então a mudança precisa já ter
    sido aplicada. Levantar aqui deixa a transação sem commit, e o `close` da
    dependência do FastAPI desfaz tudo.

    Recebe a classe de erro a levantar, como `validar_coerencia` — o serviço
    não conhece HTTP.
    """
    ids = {i for i in ids if i is not None}
    if not ids:
        return

    caixinhas = db.query(Caixinha).filter(Caixinha.id.in_(ids)).all()
    atuais = saldos(caixinhas, db)

    for caixinha in caixinhas:
        resultante = atuais.get(caixinha.id, ZERO)
        if resultante < ZERO:
            raise erro(
                f"Esta operação deixaria a caixinha '{caixinha.nome}' negativa "
                f"em {_reais(-resultante)}. Uma caixinha é uma parte do que a "
                "conta já guardou, não um limite de crédito."
            )


def _reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def guardado_sem_caixinha(conta_id: int, db: Session) -> Decimal:
    """O guardado da conta que ainda não tem rótulo de caixinha.

    É o teto para o `saldo_inicial` de uma caixinha nova: acima disso, a
    caixinha estaria reivindicando dinheiro que a conta não guardou.
    """
    ativas = ativas_da_conta(conta_id, db)
    comprometido = sum(saldos(ativas, db).values(), ZERO)
    return guardado_da_conta(conta_id, db) - comprometido
