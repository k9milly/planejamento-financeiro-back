"""Compra parcelada no cartão de crédito (ADR-14).

As N parcelas nascem **todas de uma vez**, como `Lancamento` comum. Isso não é
detalhe de implementação: uma parcela de cartão é dívida já assumida no ato da
compra, diferente de um gasto fixo que pode variar ou ser pulado. Gerar sob
demanda esconderia da pessoa um compromisso que já existe — o oposto do saldo
inteligente que motivou o ADR-0002.

Consequência boa: `services/calculos.py` não muda nada. Fatura, saldo e "quanto
devo no cartão" continuam somando lançamentos, e uma parcela de março entra na
conta de março porque é a data dela, igual a qualquer lançamento futuro já se
comporta.

O cálculo do valor de cada parcela mora aqui, e não no frontend, para não haver
duas implementações da mesma conta divergindo quando uma for corrigida.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import obter_ano_editavel
from app.models import (
    Ano,
    Categoria,
    CompraParcelada,
    Conta,
    Lancamento,
    ModoJuros,
    TipoConta,
    TipoLancamento,
)
from app.schemas import CompraParceladaCriar, CompraParceladaOut, FormaPagamento

router = APIRouter(prefix="/anos/{ano}/compras-parceladas", tags=["compras parceladas"])

CENTAVO = Decimal("0.01")


def _erro(mensagem: str, codigo: int = status.HTTP_422_UNPROCESSABLE_CONTENT):
    return HTTPException(status_code=codigo, detail=mensagem)


def _arredondar(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular(dados: CompraParceladaCriar) -> tuple[Decimal, Decimal]:
    """Devolve `(valor_parcela, valor_total)` conforme o modo escolhido.

    `valor_total` é sempre a **soma efetiva das parcelas** — com juros, quando
    houver. No modo percentual ele é maior que o valor enviado, que é o preço à
    vista.

    Juros simples, e não Tabela Price, de propósito: a Price é mais complexa e
    ainda assim não bateria exatamente com o número do banco, porque cada um
    arredonda e compõe de um jeito. Quem quer o número exato do banco usa o
    modo `valor`, que não faz conta nenhuma. Está justificado no ADR-14 — não
    trocar por outra fórmula sem revisitar aquela decisão.
    """
    parcelas = Decimal(dados.numero_parcelas)

    if dados.modo_juros is ModoJuros.VALOR:
        # Nenhuma conta financeira: a pessoa digitou o que o cartão mostra.
        return dados.valor_parcela, dados.valor_parcela * parcelas

    if dados.modo_juros is ModoJuros.PERCENTUAL:
        juros = dados.valor_total * (dados.taxa_juros_pct / Decimal(100)) * parcelas
        total = _arredondar(dados.valor_total + juros)
    else:
        total = dados.valor_total

    return _arredondar(total / parcelas), total


def _valores_das_parcelas(comum: Decimal, total: Decimal, quantidade: int) -> list[Decimal]:
    """As N parcelas, com a última absorvendo o resto da divisão.

    R$ 100 em 3x são R$ 33,33 + R$ 33,33 + R$ 33,34 — a sobra vai para o fim,
    não some. Sem isso a soma das parcelas não fecharia com o total, e o
    `valor_total` guardado seria uma promessa que os lançamentos não cumprem.
    """
    valores = [comum] * (quantidade - 1)
    return valores + [total - sum(valores, Decimal("0"))]


def _datas_das_parcelas(primeira: date, quantidade: int) -> list[date]:
    """Uma por mês, a partir da primeira, no mesmo dia.

    Dia que não existe no mês de destino cai no último dia dele — mesmo
    tratamento que `gastos_fixos.py` já dá ao vencimento (dia 31 em fevereiro).
    """
    datas = []
    for passo in range(quantidade):
        mes_total = primeira.month - 1 + passo
        ano = primeira.year + mes_total // 12
        mes = mes_total % 12 + 1
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        datas.append(date(ano, mes, min(primeira.day, ultimo_dia)))
    return datas


def _garantir_anos(datas: list[date], db: Session) -> dict[int, Ano]:
    """Cria os anos que faltarem para as parcelas futuras.

    A parcela é dívida real e já assumida; deixá-la "perdida" à espera de a
    pessoa lembrar de criar o ano seguinte seria esconder um compromisso. O ano
    nasce igual ao que `POST /anos` produziria sem saldos informados: zerado.

    A exceção é o ano que **já existe e está arquivado** — aí a compra inteira
    é recusada, em vez de desarquivar sozinha. Deve ser raríssimo: parcelas
    seguem sempre para a frente.
    """
    por_ano: dict[int, Ano] = {}
    for ano_numero in sorted({d.year for d in datas}):
        registro = db.query(Ano).filter(Ano.ano == ano_numero).one_or_none()
        if registro is None:
            registro = Ano(ano=ano_numero)
            db.add(registro)
            db.flush()
        elif registro.arquivado:
            raise _erro(
                f"Não é possível parcelar até {ano_numero}, que já está "
                "arquivado."
            )
        por_ano[ano_numero] = registro
    return por_ano


def _validar_cartao(conta_id: int, db: Session) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise _erro(f"Conta {conta_id} não existe.")
    if conta.tipo is not TipoConta.CARTAO_CREDITO:
        raise _erro(
            f"'{conta.nome}' não é um cartão de crédito. Parcelamento só existe "
            "em compra no crédito."
        )
    return conta


def _com_parcelas(compra: CompraParcelada, db: Session) -> CompraParceladaOut:
    parcelas = (
        db.query(Lancamento)
        .options(joinedload(Lancamento.categoria), joinedload(Lancamento.conta))
        .filter(Lancamento.compra_parcelada_id == compra.id)
        .order_by(Lancamento.numero_parcela)
        .all()
    )
    return CompraParceladaOut.model_validate(
        {**compra.__dict__, "parcelas": parcelas}, from_attributes=True
    )


@router.post(
    "",
    response_model=CompraParceladaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma compra parcelada e gera todas as parcelas",
)
def criar(
    dados: CompraParceladaCriar,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> CompraParceladaOut:
    _validar_cartao(dados.conta_id, db)

    if dados.categoria_id is not None and db.get(Categoria, dados.categoria_id) is None:
        raise _erro(f"Categoria {dados.categoria_id} não existe.")

    if dados.data_primeira_parcela.year != ano_ref.ano:
        raise _erro(
            f"A primeira parcela é de {dados.data_primeira_parcela.year}, mas a "
            f"compra está sendo lançada em {ano_ref.ano}."
        )

    valor_parcela, valor_total = calcular(dados)
    datas = _datas_das_parcelas(dados.data_primeira_parcela, dados.numero_parcelas)
    anos = _garantir_anos(datas, db)

    compra = CompraParcelada(
        descricao=dados.descricao,
        conta_id=dados.conta_id,
        categoria_id=dados.categoria_id,
        numero_parcelas=dados.numero_parcelas,
        tem_juros=dados.tem_juros,
        modo_juros=dados.modo_juros,
        taxa_juros_pct=dados.taxa_juros_pct,
        valor_parcela=valor_parcela,
        valor_total=valor_total,
    )
    db.add(compra)
    db.flush()

    valores = _valores_das_parcelas(valor_parcela, valor_total, dados.numero_parcelas)
    for numero, (quando, valor) in enumerate(zip(datas, valores), start=1):
        db.add(
            Lancamento(
                ano_id=anos[quando.year].id,
                conta_id=dados.conta_id,
                mes=quando.month,
                data=quando,
                valor=valor,
                tipo=TipoLancamento.SAIDA,
                forma_pagamento=FormaPagamento.CREDITO,
                categoria_id=dados.categoria_id,
                descricao=f"{dados.descricao} ({numero}/{dados.numero_parcelas})",
                compra_parcelada_id=compra.id,
                numero_parcela=numero,
            )
        )

    db.commit()
    db.refresh(compra)
    return _com_parcelas(compra, db)


@router.delete(
    "/{compra_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desfaz a compra inteira, apagando as parcelas restantes",
)
def excluir(
    compra_id: int,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> None:
    """Apaga o grupo; o `CASCADE` leva junto as parcelas em qualquer ano.

    É a ação "a compra inteira foi desfeita" — devolução, quitação antecipada.
    Para corrigir **uma** parcela (o extrato veio diferente num mês), o caminho
    continua sendo `PATCH`/`DELETE /anos/{ano}/lancamentos/{id}`, sem regra
    nova: a parcela é um lançamento como outro qualquer.
    """
    compra = db.get(CompraParcelada, compra_id)
    if compra is None:
        raise _erro(f"Compra parcelada {compra_id} não existe.", status.HTTP_404_NOT_FOUND)

    db.delete(compra)
    db.commit()
