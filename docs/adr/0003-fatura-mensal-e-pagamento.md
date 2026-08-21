# ADR-0003 — Fatura do cartão como entidade mensal, no molde de `GastoFixoMensal`

**Status:** implementado

## Contexto

Depois do ADR-0002, "quanto devo no cartão" já existe como número — é
`-saldo` da conta-cartão no fechamento do mês (`por_conta[cartao_id].saldo`,
que `calcular_totais_mes` já calcula). Falta modelar duas coisas que esse
número sozinho não dá: o **vencimento** (para o lembrete no calendário) e o
**ato de pagar** (que precisa gerar o lançamento de transferência do
ADR-0002 e saber se aquele mês já foi pago, para não pagar duas vezes).

O sistema já resolveu exatamente esse problema para gastos fixos:
`GastoFixo` (o modelo) + `GastoFixoMensal` (pago/pendente por mês,
apontando para o lançamento gerado) + as rotas `pagar`/`desfazer`, que são
idempotentes.

## Decisão

1. **Vencimento**: campo `dia_vencimento_fatura` (1–31) na própria `Conta`
   — editável pelo `PATCH /contas/{id}` que já existe, sem endpoint novo.
2. **Situação mensal**: nova tabela `FaturaMensal`
   (`cartao_id, ano_id, mes, situacao, lancamento_id`), única em
   `(cartao_id, ano_id, mes)` — o mesmo desenho de `GastoFixoMensal`, só que
   por cartão em vez de por gasto fixo, porque o cartão (assim como a
   conta) é global e não pertence a um ano.
3. **Pagar/desfazer**: `POST /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/pagar`
   e `.../desfazer`, espelhando `gastos_fixos.py` linha a linha:
   - `pagar` calcula o valor em aberto (reaproveitando
     `services/calculos.py`, sem duplicar a soma), cria a `TRANSFERENCIA`
     (origem = conta escolhida ou `conta_pagamento_padrao_id`, destino =
     cartão), marca `FaturaMensal.situacao=pago` e guarda o
     `lancamento_id`. Chamar duas vezes devolve o mesmo lançamento.
   - `desfazer` apaga o lançamento gerado e volta para `pendente`.
4. **Lembrete no calendário**: `CalendarioVencimentos.tsx` ganha uma
   segunda fonte de vencimentos (cartões, além de gastos fixos), plotados
   no dia `dia_vencimento_fatura` de cada mês, com uma cor própria para não
   se confundir com gasto fixo. Clicar alterna pago/pendente do mesmo jeito.

## Por que não calcular "em aberto" a partir de um campo guardado

O valor da fatura não é armazenado em lugar nenhum — é sempre recalculado a
partir dos lançamentos (via `calcular_ano`/`calcular_totais_mes`), do mesmo
jeito que o saldo de qualquer conta. Guardar um "total da fatura" à parte
criaria uma segunda fonte de verdade que pode se desencontrar da primeira
(por exemplo, se um lançamento de compra no crédito for editado ou
apagado depois). O projeto já evita exatamente esse tipo de duplicação —
é por isso que `services/calculos.py` é uma função pura sobre os
lançamentos, e não algo incrementado a cada escrita.

## O que fica fora do escopo (de propósito)

Cartão de crédito de verdade tem **dois** dias: o fechamento (quando a
fatura para de aceitar novas compras) e o vencimento (quando ela precisa
ser paga). O pedido original só menciona vencimento, e modelar fechamento
exigiria decidir em que mês uma compra do dia 28 "cai" — uma regra a mais
que não foi pedida. Por isso, v1 mostra sempre a fatura **em aberto até
agora** (tudo que ainda não foi pago), não "a fatura do ciclo fechado". Se
depois for necessário simular o extrato do banco com precisão de
fechamento, isso é uma extensão natural (um campo `dia_fechamento` a mais),
não uma mudança de arquitetura — vale abrir um ADR novo quando/se isso for
pedido.

## Consequências

- `FaturaMensal` precisa de `ano_id` (diferente de `GastoFixoMensal`, que
  pega o ano emprestado de `GastoFixo.ano_id`) porque o cartão, como a
  conta, é global — o mesmo cartão existe em todos os anos.
- A exclusão de uma conta-cartão com faturas pagas segue a mesma regra que
  já existe para conta comum (`routers/contas.py::excluir`): desativa em
  vez de apagar, porque apagar destruiria o histórico dos lançamentos
  gerados.
- Testes novos em `test_calculos.py` (o valor em aberto bate com a soma dos
  lançamentos de crédito menos pagamentos) e em `test_api.py`
  (idempotência de pagar/desfazer, no molde dos testes que já existem para
  gastos fixos).

## Alternativas consideradas

- **Um único lançamento por fatura, criado antecipadamente.** Rejeitada:
  exigiria saber o valor da fatura antes de todas as compras do mês
  acontecerem, o que é impossível — a fatura só é conhecida depois.
- **Marcar "pago" diretamente na `Conta`, sem tabela mensal.** Rejeitada:
  perderia o histórico mês a mês (não daria para saber se a fatura de
  março, especificamente, foi paga) e quebraria a idempotência que o botão
  de pagar precisa.
