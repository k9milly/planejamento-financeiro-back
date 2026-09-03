"""Caixinhas: as divisões nomeadas da reserva de uma conta (ADR-10).

Vive sob `/contas/{conta_id}` porque uma caixinha não existe fora de uma conta
— é o mesmo recorte que o banco da Kamilly usa, onde as caixinhas são do
Mercado Pago, especificamente.

Nenhuma rota aqui cria dinheiro. `saldo_inicial` dá nome a dinheiro que a
conta **já** tem guardado, e a transferência realoca entre duas caixinhas da
mesma conta. Quem faz o dinheiro entrar ou sair da reserva continua sendo o
lançamento, em `/anos/{ano}/lancamentos`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Ano,
    Caixinha,
    Conta,
    Lancamento,
    MetaPoupanca,
    TipoConta,
    TipoLancamento,
)
from app.schemas import (
    CaixinhaAtualizar,
    CaixinhaCriar,
    CaixinhaOut,
    TransferenciaCaixinha,
)
from app.services.caixinhas import (
    garantir_nao_negativas,
    guardado_sem_caixinha,
    saldos,
)

router = APIRouter(prefix="/contas/{conta_id}/caixinhas", tags=["caixinhas"])


def _erro(mensagem: str, codigo: int = status.HTTP_422_UNPROCESSABLE_CONTENT):
    return HTTPException(status_code=codigo, detail=mensagem)


def _reais(valor: Decimal) -> str:
    """Formata para a mensagem de erro. Quem lê precisa do número, não da regra."""
    return f"R$ {valor:.2f}".replace(".", ",")


def _obter_conta(conta_id: int, db: Session) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise _erro(f"Conta {conta_id} não existe.", status.HTTP_404_NOT_FOUND)
    return conta


def _obter(conta_id: int, caixinha_id: int, db: Session) -> Caixinha:
    caixinha = (
        db.query(Caixinha)
        .filter(Caixinha.id == caixinha_id, Caixinha.conta_id == conta_id)
        .one_or_none()
    )
    if caixinha is None:
        raise _erro(
            f"Caixinha {caixinha_id} não existe nesta conta.",
            status.HTTP_404_NOT_FOUND,
        )
    return caixinha


def _validar_meta(meta_id: int | None, db: Session) -> None:
    if meta_id is None:
        return
    meta = db.get(MetaPoupanca, meta_id)
    if meta is None:
        raise _erro(f"Meta {meta_id} não existe.")
    if not meta.ativa:
        raise _erro(
            f"A meta {meta_id} está desativada — vincule a caixinha a uma meta "
            "em vigor."
        )


def _saida(caixinha: Caixinha, db: Session) -> CaixinhaOut:
    return _saidas([caixinha], db)[0]


def _saidas(caixinhas: list[Caixinha], db: Session) -> list[CaixinhaOut]:
    """Monta a resposta em uma passada — o saldo não é coluna, é calculado."""
    atuais = saldos(caixinhas, db)
    return [
        CaixinhaOut(
            id=c.id,
            conta_id=c.conta_id,
            nome=c.nome,
            meta_id=c.meta_id,
            saldo=atuais.get(c.id, Decimal("0.00")),
            criada_em=c.criada_em,
            ativa=c.ativa,
        )
        for c in caixinhas
    ]


@router.get("", response_model=list[CaixinhaOut], summary="Lista as caixinhas da conta")
def listar(
    conta_id: int, incluir_inativas: bool = False, db: Session = Depends(get_db)
) -> list[CaixinhaOut]:
    _obter_conta(conta_id, db)
    consulta = db.query(Caixinha).filter(Caixinha.conta_id == conta_id)
    if not incluir_inativas:
        consulta = consulta.filter(Caixinha.ativa.is_(True))
    return _saidas(consulta.order_by(Caixinha.criada_em, Caixinha.id).all(), db)


@router.post(
    "",
    response_model=CaixinhaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma caixinha na conta",
)
def criar(
    conta_id: int, dados: CaixinhaCriar, db: Session = Depends(get_db)
) -> CaixinhaOut:
    """`saldo_inicial` não pode passar do guardado que ainda não tem caixinha.

    Sem esse teto, criar caixinhas seria uma forma de inventar reserva: a soma
    das caixinhas passaria do que a conta de fato guardou, e o "guardado sem
    caixinha" ficaria negativo.
    """
    conta = _obter_conta(conta_id, db)
    if conta.tipo is not TipoConta.CORRENTE:
        raise _erro(
            "Um cartão de crédito não tem reserva, então não pode ter caixinha. "
            "Crie a caixinha na conta corrente."
        )

    _validar_meta(dados.meta_id, db)

    if dados.saldo_inicial > 0:
        disponivel = guardado_sem_caixinha(conta_id, db)
        if dados.saldo_inicial > disponivel:
            raise _erro(
                f"Esta conta tem {_reais(disponivel)} guardado ainda sem "
                f"caixinha, e você pediu {_reais(dados.saldo_inicial)}. O saldo "
                "inicial serve para dar nome a dinheiro que já está guardado, "
                "não para acrescentar."
            )

    caixinha = Caixinha(conta_id=conta_id, **dados.model_dump())
    db.add(caixinha)
    db.commit()
    db.refresh(caixinha)
    return _saida(caixinha, db)


@router.patch(
    "/{caixinha_id}", response_model=CaixinhaOut, summary="Edita nome ou meta vinculada"
)
def atualizar(
    conta_id: int,
    caixinha_id: int,
    dados: CaixinhaAtualizar,
    db: Session = Depends(get_db),
) -> CaixinhaOut:
    caixinha = _obter(conta_id, caixinha_id, db)
    alteracoes = dados.model_dump(exclude_unset=True)

    if "meta_id" in alteracoes:
        _validar_meta(alteracoes["meta_id"], db)

    for campo, valor in alteracoes.items():
        setattr(caixinha, campo, valor)

    db.commit()
    db.refresh(caixinha)
    return _saida(caixinha, db)


@router.delete(
    "/{caixinha_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativa a caixinha (o saldo volta a ser guardado sem caixinha)",
)
def desativar(conta_id: int, caixinha_id: int, db: Session = Depends(get_db)) -> None:
    """Nunca apaga: desativar solta o rótulo, não o dinheiro.

    Como o saldo é derivado das caixinhas **ativas**, sair dessa lista já
    devolve o valor ao "guardado sem caixinha" da conta — não há acerto de
    contas a fazer aqui. Os lançamentos que apontam para ela continuam
    apontando, e é por isso que o vínculo é `RESTRICT`: apagar a linha
    deixaria lançamentos órfãos e mudaria totais de meses já fechados.
    """
    caixinha = _obter(conta_id, caixinha_id, db)
    caixinha.ativa = False
    db.commit()


@router.post(
    "/transferir",
    response_model=CaixinhaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Move dinheiro entre duas caixinhas da mesma conta",
)
def transferir(
    conta_id: int, dados: TransferenciaCaixinha, db: Session = Depends(get_db)
) -> CaixinhaOut:
    """Cria um lançamento `transferencia_caixinha`; devolve a caixinha de destino.

    Vira lançamento — e não uma edição de saldo — para a realocação ficar no
    histórico como qualquer outra movimentação. Mas é o único tipo que não
    conta como entrada nem saída do período e não muda o guardado da conta: o
    dinheiro não saiu de lugar nenhum, só trocou de rótulo.
    """
    _obter_conta(conta_id, db)

    if dados.caixinha_origem_id == dados.caixinha_destino_id:
        raise _erro("A caixinha de destino precisa ser diferente da de origem.")

    origem = _obter(conta_id, dados.caixinha_origem_id, db)
    destino = _obter(conta_id, dados.caixinha_destino_id, db)
    for caixinha in (origem, destino):
        if not caixinha.ativa:
            raise _erro(
                f"A caixinha '{caixinha.nome}' está desativada e não pode "
                "receber nem enviar dinheiro."
            )

    # Conferido aqui para a mensagem poder dizer quanto há na origem; a trava
    # geral abaixo é que garante a regra, e vale para todo caminho que mexe em
    # caixinha.
    disponivel = saldos([origem], db)[origem.id]
    if dados.valor > disponivel:
        raise _erro(
            f"A caixinha '{origem.nome}' tem {_reais(disponivel)}, e você pediu "
            f"para mover {_reais(dados.valor)}."
        )

    hoje = date.today()
    ano_ref = db.query(Ano).filter(Ano.ano == hoje.year).one_or_none()
    if ano_ref is None:
        raise _erro(
            f"O ano {hoje.year} ainda não existe no sistema. Crie-o antes de "
            "movimentar caixinhas."
        )
    if ano_ref.arquivado:
        raise _erro(
            f"O ano {hoje.year} está arquivado e não aceita novos lançamentos.",
            status.HTTP_409_CONFLICT,
        )

    db.add(
        Lancamento(
            ano_id=ano_ref.id,
            conta_id=conta_id,
            mes=hoje.month,
            data=hoje,
            valor=dados.valor,
            tipo=TipoLancamento.TRANSFERENCIA_CAIXINHA,
            caixinha_id=origem.id,
            caixinha_destino_id=destino.id,
            descricao=f"{origem.nome} → {destino.nome}",
        )
    )
    db.flush()
    garantir_nao_negativas({origem.id, destino.id}, db, _erro)
    db.commit()
    return _saida(destino, db)
