# ADR-0002 — Cartão de crédito é uma `Conta` de tipo `cartao_credito`; compra no crédito é lançada nela, não na conta real

**Status:** implementado

## Contexto

O pedido tem duas partes que parecem separadas mas são a mesma decisão:

1. "Saldo inteligente": o saldo mostrado deve refletir o dinheiro que
   realmente está disponível — uma compra no crédito não pode descontar do
   saldo até a fatura ser paga.
2. Poder escolher *em qual* cartão a compra no crédito foi feita ("cartão
   do Mercado Pago, ou algum outro").

`Conta` já existe e já é exatamente o conceito de "onde o dinheiro está":
tem nome, cor, saldo, guardado, e é global (não por ano). O sistema também
já tem `TipoLancamento.TRANSFERENCIA`, cujo efeito é `saldo origem -= valor`
e `saldo destino += valor` — mover dinheiro entre duas contas suas sem que
isso conte como entrada ou saída.

## Decisão

Um cartão de crédito **é uma `Conta`**, com um campo novo `tipo`
(`corrente` | `cartao_credito`, default `corrente`). Uma compra no crédito é
um `Lancamento` do tipo `saida` cujo `conta_id` aponta para a conta-cartão,
não para a conta real de onde o dinheiro vai sair depois.

Isso faz duas coisas de graça, sem código novo em `services/calculos.py`:

- **O saldo real não é tocado.** `calcular_totais_mes` já faz
  `conta.saldo -= valor` *na conta do lançamento*. Se o lançamento aponta
  para o cartão, é o saldo do cartão que cai — nunca o da conta corrente.
- **O saldo do cartão vira a fatura em aberto, de graça.** Como o cartão
  começa em zero e só recebe débitos, seu "saldo" fica cada vez mais
  negativo — e `-saldo_do_cartão` é exatamente "quanto devo". Pagar a
  fatura é uma `TRANSFERENCIA` da conta real para o cartão: o saldo da
  conta real cai (dinheiro saiu de verdade) e o saldo do cartão sobe de
  volta em direção a zero (a dívida diminui). O mecanismo de transferência
  já existe e já é testado — só ganha um novo uso.

Regra de coerência nova (em `validar_coerencia`, que passa a receber o tipo
da conta, não só o id):

| Situação | `conta_id` (origem) | `conta_destino_id` |
| --- | --- | --- |
| `saida` com `forma_pagamento=credito` | precisa ser `cartao_credito` | — |
| `saida` com débito/pix/dinheiro/nulo | precisa ser `corrente` | — |
| `entrada`, `guardado`, `retirado`, `rendimento`, `perda` | precisa ser `corrente` | — |
| `transferencia` (pagamento de fatura) | precisa ser `corrente` | pode ser `corrente` ou `cartao_credito` |
| `transferencia` comum | precisa ser `corrente` | precisa ser `corrente` |

Em outras palavras: dinheiro só **sai** de uma conta-cartão através de um
pagamento de fatura (a origem de uma transferência nunca é um cartão); ele
só **entra** numa conta-cartão como despesa no crédito ou como pagamento de
fatura.

`Conta` ganha também `conta_pagamento_padrao_id` (opcional, self-referencial,
só relevante quando `tipo=cartao_credito`): qual conta real normalmente paga
esse cartão. Pré-preenche a tela de pagamento de fatura (ver ADR-0003); o
usuário pode escolher outra conta na hora, se quiser.

## Por que reaproveitar `Conta`, e não criar uma entidade `Cartao` separada

- O CRUD de contas já existe de ponta a ponta — `routers/contas.py`,
  `GerenciadorContas.tsx`, exclusão que desativa em vez de apagar quando há
  uso. Duplicar isso para `Cartao` seria manter duas telas e dois endpoints
  quase idênticos.
- `SaldoInicial` já modela "quanto uma conta tinha antes do primeiro
  lançamento do ano" — e isso é útil para cartão também: quem começar a
  usar o app no meio de uma fatura em aberto define o saldo inicial do
  cartão como um número negativo (a dívida que já existia), do mesmo jeito
  que define o saldo inicial de uma conta corrente.
- O encadeamento de saldos entre anos (arquivar um ano copia o fechamento
  como abertura do seguinte) passa a valer para a dívida do cartão
  automaticamente — sem nenhum código a mais.
- O pedido de "criar uma forma de adicionar contas" (item 3 do usuário) e o
  de "cartão do Mercado Pago, ou algum outro" (item 2) são o mesmo CRUD com
  um campo `tipo` a mais. Resolver os dois com uma única extensão evita
  duas features fazendo a mesma coisa com nomes diferentes.

## Consequências

- Toda soma "quanto tenho no total" (patrimônio, em `GerenciadorContas.tsx`;
  `saldo` agregado, em `TotaisMes.tsx`/`ResumoMesOut`) precisa passar a
  **excluir** contas do tipo `cartao_credito` — senão a dívida do cartão
  entraria na conta como se fosse dinheiro negativo seu, o que até é
  verdade patrimonialmente, mas não é o que "saldo inteligente" pediu (ver
  spec "Saldo inteligente" para o detalhe de onde cada soma muda).
- `GerenciadorContas.tsx` passa a mostrar dois grupos: "Contas" (saldo +
  guardado, como hoje) e "Cartões de crédito" (fatura em aberto, vencimento).
- O formulário de novo lançamento (`FormularioLancamento.tsx`) passa a
  filtrar a lista de contas pelo `tipo` compatível com a combinação
  tipo+forma de pagamento escolhida — ver tabela acima.
- `RETIRADO`/`GUARDADO`/`RENDIMENTO`/`PERDA` continuam proibidos numa
  conta-cartão. Um cartão não tem "reserva" — `guardado` nele fica sempre
  zero.

## Alternativas consideradas

- **Entidade `CartaoCredito` separada, com FK para a conta que paga.**
  Mais "correta" no sentido de que um cartão não é literalmente uma carteira
  de dinheiro — mas exige duplicar CRUD, endpoints e telas, e perde de graça
  o encadeamento de saldo entre anos e o reaproveitamento da transferência
  para pagamento de fatura. Rejeitada por custo maior sem ganho para o que
  foi pedido.
- **Compra no crédito lançada na conta real, com uma flag "pendente".**
  Exigiria que `calcular_totais_mes` soubesse ignorar lançamentos
  "pendentes" ao somar saldo, mas contá-los em algum outro total — mais
  regra nova espalhada pelo cálculo, contra menos regra nova reaproveitando
  o que já existe. Rejeitada.
