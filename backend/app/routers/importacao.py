"""Importação de extrato bancário em OFX, CSV ou XLSX.

O fluxo tem dois passos de propósito: **prévia** e **confirmação**. Nada é
gravado no primeiro. Um extrato traz transações que o app não consegue
classificar sozinho — um Pix recebido pode ser salário ou devolução de um
amigo, e uma transferência para a poupança parece uma saída comum. Quem decide
é o usuário, na tela de revisão.

O formato do arquivo só importa na primeira linha da prévia, onde um leitor é
escolhido; da leitura em diante tudo é `TransacaoExtrato` e o resto do fluxo —
dedupe, sugestão de categoria, confirmação — é o mesmo para os três (ADR-08).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import obter_ano_editavel
from app.models import (
    Ano,
    Categoria,
    Conta,
    Lancamento,
    RegraCategorizacao,
    TipoLancamento,
)
from app.schemas import (
    ConfirmarImportacao,
    PreviaImportacao,
    ResultadoImportacao,
    TransacaoPrevia,
    validar_coerencia,
    validar_conta_compativel,
)
from app.services.extrato import ErroExtrato, TransacaoExtrato
from app.services.ofx import ler_ofx
from app.services.tabular import ler_csv, ler_xlsx

router = APIRouter(prefix="/anos/{ano}/importacao", tags=["importação"])

# Extratos são arquivos pequenos; qualquer coisa maior que isso não é um
# extrato e não vale a pena carregar na memória.
TAMANHO_MAXIMO = 10 * 1024 * 1024

Formato = Literal["ofx", "csv", "xlsx"]

LEITORES: dict[str, Callable[[bytes], list[TransacaoExtrato]]] = {
    "ofx": ler_ofx,
    "csv": ler_csv,
    "xlsx": ler_xlsx,
}


def normalizar(texto: str) -> str:
    """Maiúsculas e sem acento, para casar regras independente de digitação."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).upper()


def _sugerir_categoria(
    descricao: str, regras: list[tuple[str, Categoria]]
) -> Categoria | None:
    """Regra cujo padrão aparece na descrição.

    Em empate, vence o padrão mais longo — o mais específico. Sem isso, uma
    regra genérica como "MERCADO" ganharia de "MERCADO LIVRE" por acaso da
    ordem de inserção.

    Recebe pares já normalizados em vez das entidades: normalizar o atributo do
    objeto ORM o marcaria como alterado e o SQLAlchemy gravaria a mudança no
    banco no próximo flush.
    """
    alvo = normalizar(descricao)
    candidatas = [(p, c) for p, c in regras if p in alvo]
    if not candidatas:
        return None
    return max(candidatas, key=lambda par: len(par[0]))[1]


@router.post(
    "/previa",
    response_model=PreviaImportacao,
    summary="Lê um extrato e devolve a prévia, sem gravar nada",
)
async def previa(
    arquivo: UploadFile = File(..., description="Extrato exportado pelo banco"),
    formato: Formato = Form(..., description="Formato do arquivo enviado"),
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> PreviaImportacao:
    conteudo = await arquivo.read()

    if not conteudo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O arquivo está vazio.",
        )
    if len(conteudo) > TAMANHO_MAXIMO:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Arquivo muito grande para ser um extrato.",
        )

    try:
        transacoes = LEITORES[formato](conteudo)
    except ErroExtrato as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(erro)
        ) from erro

    existentes = db.query(Lancamento).filter(Lancamento.ano_id == ano_ref.id).all()
    fitids = {lanc.fitid for lanc in existentes if lanc.fitid}
    # Chave de "parece o mesmo": data e valor batem, mas veio de outra origem.
    assinaturas = {(lanc.data, lanc.valor) for lanc in existentes}

    # Normaliza uma vez só, fora do laço por transação.
    regras = [
        (normalizar(r.padrao), r.categoria) for r in db.query(RegraCategorizacao).all()
    ]

    linhas: list[TransacaoPrevia] = []
    ja_importadas = 0

    for transacao in transacoes:
        duplicado = transacao.fitid in fitids
        if duplicado:
            ja_importadas += 1

        categoria = (
            _sugerir_categoria(transacao.descricao, regras)
            if transacao.saida
            else None
        )

        linhas.append(
            TransacaoPrevia(
                fitid=transacao.fitid,
                data=transacao.data,
                valor=transacao.valor,
                descricao=transacao.descricao,
                tipo_sugerido=(
                    TipoLancamento.SAIDA if transacao.saida else TipoLancamento.ENTRADA
                ),
                categoria_sugerida_id=categoria.id if categoria else None,
                categoria_sugerida_nome=categoria.nome if categoria else None,
                duplicado=duplicado,
                possivel_repetido=(
                    not duplicado
                    and (transacao.data, transacao.valor) in assinaturas
                ),
                fora_do_ano=transacao.data.year != ano_ref.ano,
            )
        )

    return PreviaImportacao(
        total_lidas=len(transacoes),
        ja_importadas=ja_importadas,
        transacoes=linhas,
    )


@router.post(
    "/confirmar",
    response_model=ResultadoImportacao,
    status_code=status.HTTP_201_CREATED,
    summary="Grava as transações revisadas",
)
def confirmar(
    dados: ConfirmarImportacao,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> ResultadoImportacao:
    """Cria os lançamentos aprovados.

    Revalida os duplicados no servidor: entre a prévia e a confirmação o
    usuário pode ter importado o mesmo extrato em outra aba.
    """
    fitids = {
        lanc.fitid
        for lanc in db.query(Lancamento).filter(Lancamento.ano_id == ano_ref.id)
        if lanc.fitid
    }

    importadas = 0
    ignoradas = 0
    regras_criadas = 0

    for item in dados.transacoes:
        if item.fitid in fitids:
            ignoradas += 1
            continue

        if item.data.year != ano_ref.ano:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"A transação de {item.data.isoformat()} não pertence a "
                    f"{ano_ref.ano}. Ajuste a data ou importe no ano correto."
                ),
            )

        _validar_coerencia(item)
        _validar_conta_compativel(item, db)

        db.add(
            Lancamento(
                ano_id=ano_ref.id,
                conta_id=item.conta_id,
                conta_destino_id=item.conta_destino_id,
                mes=item.data.month,
                data=item.data,
                valor=item.valor,
                tipo=item.tipo,
                destino=item.destino,
                categoria_id=item.categoria_id,
                forma_pagamento=item.forma_pagamento,
                descricao=item.descricao,
                fitid=item.fitid,
            )
        )
        fitids.add(item.fitid)
        importadas += 1

        if item.aprender_padrao and item.categoria_id:
            if _criar_regra(db, item.aprender_padrao, item.categoria_id):
                regras_criadas += 1

    db.commit()
    return ResultadoImportacao(
        importadas=importadas,
        ignoradas_duplicadas=ignoradas,
        regras_criadas=regras_criadas,
    )


def _validar_coerencia(item) -> None:
    """Mesmas regras do cadastro manual — a importação não é uma porta dos fundos."""

    def erro(mensagem: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=mensagem
        )

    validar_coerencia(
        item.tipo,
        item.destino,
        item.categoria_id,
        item.conta_id,
        item.conta_destino_id,
        item.forma_pagamento,
        erro,
    )


def _validar_conta_compativel(item, db: Session) -> None:
    def erro(mensagem: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=mensagem
        )

    conta = db.get(Conta, item.conta_id)
    if conta is None:
        raise erro(f"Conta {item.conta_id} não existe.")
    validar_conta_compativel(item.tipo, item.forma_pagamento, conta.tipo, erro)


def _criar_regra(db: Session, padrao: str, categoria_id: int) -> bool:
    """Cria a regra se ela ainda não existir. Devolve se criou."""
    normalizado = normalizar(padrao.strip())
    if len(normalizado) < 2:
        return False
    existe = (
        db.query(RegraCategorizacao)
        .filter(RegraCategorizacao.padrao == normalizado)
        .one_or_none()
    )
    if existe:
        existe.categoria_id = categoria_id
        return False
    db.add(RegraCategorizacao(padrao=normalizado, categoria_id=categoria_id))
    return True
