"""O levantamento de produção da Fase 15, contra um banco descartável.

Ele serve para decidir se dado real precisa ser corrigido. Um levantamento
que ninguém testou não é base para essa decisão — se ele contasse errado,
o erro iria direto para a conversa sobre mexer no banco de produção.

Dois pontos: só lê, e acha o que tem que achar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import (
    Ano,
    Conta,
    Espaco,
    Lancamento,
    TipoConta,
    TipoLancamento,
)
from scripts.levantar_parcelas_e_faturas import principal


def _montar(db):
    espaco = Espaco(nome="Casa")
    db.add(espaco)
    db.flush()

    ano = Ano(ano=2026, espaco_id=espaco.id)
    corrente = Conta(nome="Nubank", espaco_id=espaco.id)
    cartao = Conta(
        nome="Cartao MP",
        tipo=TipoConta.CARTAO_CREDITO,
        dia_vencimento_fatura=10,
        espaco_id=espaco.id,
    )
    db.add_all([ano, corrente, cartao])
    db.flush()

    def lancar(**campos):
        db.add(
            Lancamento(
                ano_id=ano.id,
                espaco_id=espaco.id,
                valor=Decimal("10.00"),
                **campos,
            )
        )

    # Duas parcelas importadas com a regra antiga, e uma primeira parcela,
    # que está no lugar certo e não deve ser listada.
    lancar(
        conta_id=cartao.id,
        mes=7,
        data=date(2026, 7, 26),
        tipo=TipoLancamento.SAIDA,
        descricao="LOJA Parcela 3 de 4",
    )
    lancar(
        conta_id=cartao.id,
        mes=8,
        data=date(2026, 8, 8),
        tipo=TipoLancamento.SAIDA,
        descricao="VIVARA Parcela 2 de 10",
    )
    lancar(
        conta_id=cartao.id,
        mes=9,
        data=date(2026, 9, 25),
        tipo=TipoLancamento.SAIDA,
        descricao="TikTok Parcela 1 de 3",
    )
    lancar(
        conta_id=cartao.id,
        mes=9,
        data=date(2026, 9, 8),
        tipo=TipoLancamento.SAIDA,
        descricao="JR FITNESS CENTER",
    )
    # Um pagamento de fatura, único.
    lancar(
        conta_id=corrente.id,
        conta_destino_id=cartao.id,
        mes=10,
        data=date(2026, 10, 10),
        tipo=TipoLancamento.TRANSFERENCIA,
        descricao="Pagamento da fatura",
    )
    db.commit()
    return corrente, cartao


def test_acha_so_as_parcelas_com_numero_maior_que_um(sessao_teste, capsys):
    db = sessao_teste()
    try:
        _montar(db)
    finally:
        db.close()

    assert principal(sessao_teste) == 0
    saida = capsys.readouterr().out

    assert "2 lancamento(s)" in saida
    assert "Parcela 3 de 4" in saida
    assert "Parcela 2 de 10" in saida
    # Primeira parcela e compra avulsa ficam de fora.
    assert "Parcela 1 de 3" not in saida
    assert "JR FITNESS" not in saida


def test_mostra_para_onde_cada_parcela_iria(sessao_teste, capsys):
    """A conferência que torna o levantamento útil para decidir.

    "Parcela 3 de 4" comprada em 26/07 seria cobrada em setembro.
    """
    db = sessao_teste()
    try:
        _montar(db)
    finally:
        db.close()

    principal(sessao_teste)
    saida = capsys.readouterr().out
    assert "2026-09" in saida
    assert "2026-09" in saida.split("Parcela 3 de 4")[0]


def test_diz_que_nao_alterou_nada(sessao_teste, capsys):
    db = sessao_teste()
    try:
        _montar(db)
    finally:
        db.close()

    principal(sessao_teste)
    assert "NADA FOI ALTERADO" in capsys.readouterr().out


def test_nao_escreve_no_banco(sessao_teste):
    """O que mais importa num script apontado para produção."""
    db = sessao_teste()
    try:
        _montar(db)
        antes = [
            (lanc.id, lanc.data, lanc.valor, lanc.descricao)
            for lanc in db.query(Lancamento).order_by(Lancamento.id)
        ]
    finally:
        db.close()

    principal(sessao_teste)

    db = sessao_teste()
    try:
        depois = [
            (lanc.id, lanc.data, lanc.valor, lanc.descricao)
            for lanc in db.query(Lancamento).order_by(Lancamento.id)
        ]
    finally:
        db.close()

    assert antes == depois


def test_conta_pagamento_de_fatura_e_nao_acusa_duplicata(sessao_teste, capsys):
    db = sessao_teste()
    try:
        _montar(db)
    finally:
        db.close()

    principal(sessao_teste)
    saida = capsys.readouterr().out
    assert "Nenhum duplicado" in saida
    assert "MAIS DE UM" not in saida


def test_acusa_quando_ha_dois_pagamentos_no_mesmo_mes(sessao_teste, capsys):
    """O cenário que a Kamilly temia ao clicar três vezes em "Pagar"."""
    db = sessao_teste()
    try:
        corrente, cartao = _montar(db)
        ano = db.query(Ano).one()
        db.add(
            Lancamento(
                ano_id=ano.id,
                espaco_id=ano.espaco_id,
                conta_id=corrente.id,
                conta_destino_id=cartao.id,
                mes=10,
                data=date(2026, 10, 10),
                valor=Decimal("10.00"),
                tipo=TipoLancamento.TRANSFERENCIA,
                descricao="Pagamento da fatura (de novo)",
            )
        )
        db.commit()
    finally:
        db.close()

    principal(sessao_teste)
    saida = capsys.readouterr().out
    assert "MAIS DE UM" in saida
    assert "1 par(es)" in saida
