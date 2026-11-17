"""Levantamento **somente leitura** de dois pontos pedidos na Fase 15.

Uso (em produção, depois do deploy):
    flyctl ssh console --app planejamento-financeiro \\
        -C "python -m scripts.levantar_parcelas_e_faturas"

Localmente, apontando para o banco que estiver em `DATABASE_URL`:
    python -m scripts.levantar_parcelas_e_faturas

**Este script não escreve nada.** Nenhum `INSERT`, `UPDATE` ou `DELETE`, e
nem sequer abre transação de escrita. Ele existe porque o `ADR-19` manda
olhar o dado real antes de decidir qualquer correção, e porque "corrigir
sozinho" num banco de finanças é a última coisa que se faz.

## O que ele responde

**1. Quantas parcelas importadas estão no mês errado.** Até o `ADR-19`, a
linha "Parcela N de M" era gravada com a data que a fatura imprime — a da
compra original. A fatura de outubro de 2026 já foi importada assim. As
parcelas com `N > 1` são as que ficaram num mês anterior ao de cobrança.

**2. Se o pagamento de fatura duplicou.** A Kamilly clicou em "Pagar fatura"
três vezes, porque a tela nunca atualizava (era a URL errada do frontend,
ver `ADR-20`). O pagamento é idempotente de propósito e há teste, mas uma
coisa é o teste e outra é o dado: este script conta as transferências de
pagamento por cartão e mês, e aponta qualquer par com mais de uma.
"""

from __future__ import annotations

import re
import sys
from collections import Counter

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Conta, Lancamento, TipoConta, TipoLancamento

PARCELA = re.compile(r"\bParcela\s+(\d{1,2})\s+de\s+(\d{1,2})\b", re.IGNORECASE)


def _parcelas_fora_do_mes(db) -> list[tuple[Lancamento, int, int]]:
    """Lançamentos cuja descrição diz "Parcela N de M" com `N > 1`."""
    achados = []
    for lanc in db.scalars(select(Lancamento)):
        encontrado = PARCELA.search(lanc.descricao or "")
        if encontrado is None:
            continue
        numero, total = int(encontrado.group(1)), int(encontrado.group(2))
        if numero > 1:
            achados.append((lanc, numero, total))
    return sorted(achados, key=lambda t: (t[0].data, t[0].id))


def _pagamentos_de_fatura(db) -> Counter:
    """Transferências para um cartão, agrupadas por (cartão, ano-mês)."""
    cartoes = {
        c.id: c.nome
        for c in db.scalars(select(Conta))
        if c.tipo is TipoConta.CARTAO_CREDITO
    }
    contagem: Counter = Counter()
    for lanc in db.scalars(
        select(Lancamento).where(Lancamento.tipo == TipoLancamento.TRANSFERENCIA)
    ):
        if lanc.conta_destino_id in cartoes:
            chave = (cartoes[lanc.conta_destino_id], lanc.data.year, lanc.mes)
            contagem[chave] += 1
    return contagem


def principal(abrir_sessao=None) -> int:
    """`abrir_sessao` existe só para o teste entregar um banco descartável.

    Sem ele, este script só poderia ser conferido rodando contra um banco de
    verdade — e um levantamento que ninguém testa é um levantamento em que
    não dá para confiar na hora de decidir mexer em dado real.
    """
    db = (abrir_sessao or SessionLocal)()
    try:
        print("=" * 70)
        print("1. Parcelas importadas com N > 1 (gravadas no mes da compra)")
        print("=" * 70)
        achados = _parcelas_fora_do_mes(db)
        if not achados:
            print("  Nenhuma. Nada a corrigir.")
        else:
            print(f"  {len(achados)} lancamento(s):\n")
            for lanc, numero, total in achados:
                # O deslocamento que o ADR-19 aplicaria, só para conferência.
                mes_total = lanc.data.month - 1 + (numero - 1)
                ano_destino = lanc.data.year + mes_total // 12
                mes_destino = mes_total % 12 + 1
                print(
                    f"  id={lanc.id:<5} {lanc.data}  R$ {lanc.valor:>9}  "
                    f"parcela {numero}/{total}  ->  {ano_destino}-{mes_destino:02d}"
                )
                print(f"           {lanc.descricao}")
            print(
                "\n  NADA FOI ALTERADO. Para corrigir, e preciso um script"
                "\n  proprio, com --simular antes de --aplicar."
            )

        print()
        print("=" * 70)
        print("2. Pagamentos de fatura por cartao e mes")
        print("=" * 70)
        contagem = _pagamentos_de_fatura(db)
        if not contagem:
            print("  Nenhuma transferencia para cartao encontrada.")
        else:
            duplicados = {k: v for k, v in contagem.items() if v > 1}
            for (cartao, ano, mes), quantas in sorted(contagem.items()):
                marca = "  <<< MAIS DE UM" if quantas > 1 else ""
                print(f"  {cartao:<20} {ano}-{mes:02d}  {quantas}{marca}")
            print()
            if duplicados:
                print(f"  ATENCAO: {len(duplicados)} par(es) com mais de um pagamento.")
            else:
                print("  Nenhum duplicado: a idempotencia se confirma no dado real.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(principal())
