# Regras de negócio

Referência das regras que o sistema aplica. Cada uma tem um teste
correspondente em `backend/tests/`.

## Carteiras

O sistema modela **duas carteiras**:

- **Conta** — dinheiro disponível para o dia a dia.
- **Guardado** — a reserva.

Todo lançamento afeta uma delas ou move dinheiro entre as duas. O patrimônio
total é `saldo + guardado_acumulado`.

## Tipos de conta

| Tipo | O que é | `saldo` significa |
| --- | --- | --- |
| `corrente` | Dinheiro de verdade (Nubank, Mercado Pago, espécie) | Disponível para gastar |
| `cartao_credito` | Um cartão, modelado como conta (ver ADR-0002) | Dívida — sempre ≤ 0 |

Um cartão de crédito só existe com `dia_vencimento_fatura` (1–31) preenchido;
uma conta corrente não pode ter `dia_vencimento_fatura` nem
`conta_pagamento_padrao_id`. Ver `test_criar_cartao_sem_dia_vencimento_e_rejeitado`.

## Forma de pagamento

Campo opcional em lançamentos de saída e em gastos fixos:
`credito | debito | pix | dinheiro`. `null` é tratado como `debito` em todo
lugar que olha o campo — nenhum lançamento histórico muda de comportamento
(ver ADR-0001).

| Situação | `conta_id` (origem) precisa ser |
| --- | --- |
| Saída com `forma_pagamento=credito` | `cartao_credito` |
| Saída com débito/pix/dinheiro/nulo | `corrente` |
| Qualquer outro tipo de lançamento | `corrente` |

Violar a regra devolve 422. Editar um lançamento trocando a forma de
pagamento para crédito sem trocar a conta é rejeitado do mesmo jeito — a
checagem roda sobre o objeto já mesclado do PATCH.

## Saldo inteligente

Uma compra no crédito é um lançamento de `saida` apontando para a
conta-cartão, não para a conta real (ADR-0002). Como consequência, sem
código novo em `services/calculos.py`:

- O `saldo` de uma conta corrente **não** é afetado por uma compra no
  crédito — só o saldo (a dívida) da conta-cartão, que fica em
  `por_cartao`, separado de `por_conta`.
- `por_cartao[cartao].saldo` é sempre ≤ 0; `-saldo` é a fatura em aberto.
- Pagar a fatura é uma `TRANSFERENCIA` da conta real para o cartão: o saldo
  real cai (dinheiro saiu de verdade) e o saldo do cartão sobe de volta em
  direção a zero.

Ver `test_credito_nao_desconta_saldo_da_conta` e a classe
`TestSaldoInteligente` em `test_calculos.py`.

## Fatura do cartão

- O valor em aberto **nunca é armazenado**: é sempre recalculado a partir
  dos lançamentos, do mesmo jeito que o saldo de qualquer conta (ver
  ADR-0003).
- `POST /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/pagar` cria a
  transferência e é **idempotente**: chamar duas vezes devolve o mesmo
  lançamento em vez de duplicar (mesmo padrão de `gastos_fixos.py::pagar`).
- Sem `conta_pagamento_id` no corpo e sem `conta_pagamento_padrao_id` no
  cartão, `pagar` devolve 422 — não há como pagar sem saber de onde sai o
  dinheiro.
- `desfazer` remove o lançamento gerado e volta a fatura para `pendente`.
- Excluir uma conta-cartão com faturas pagas segue a mesma regra de
  "desativar em vez de apagar" que já vale para conta comum.

## Tipos de lançamento

| Tipo | Efeito na conta | Efeito no guardado |
| --- | --- | --- |
| `entrada` | `+ valor` | — |
| `saida` | `− valor` | — |
| `guardado` | `− valor` | `+ valor` |
| `retirado` | `+ valor` | `− valor` |
| `rendimento` (destino `conta`) | `+ valor` | — |
| `rendimento` (destino `guardado`) | — | `+ valor` |

`guardado` e `retirado` são **transferências**: não alteram o patrimônio total,
só de qual carteira o dinheiro faz parte.

## Fórmulas

Para cada mês:

```
saldo = saldo_inicial
      + entradas
      + rendimento_conta
      + retirado
      − saidas
      − guardado_bruto

guardado_no_mes  = guardado_bruto + rendimento_guardado − retirado
guardado_acumulado = guardado_inicial + guardado_no_mes
```

Onde `saldo_inicial` e `guardado_inicial` são os valores de fechamento do mês
anterior. Para janeiro, são os `saldo_inicial_conta` e `saldo_inicial_guardado`
do ano.

O **total guardado** exibido no container homônimo é o `guardado_acumulado` de
dezembro, ou seja, a reserva ao fim do ano.

## Validações

### Lançamentos

| Regra | Resposta se violada |
| --- | --- |
| `valor` deve ser maior que zero | 422 |
| A data deve pertencer ao ano do lançamento | 422 |
| `destino` é obrigatório em `rendimento` | 422 |
| `destino` é proibido nos demais tipos | 422 |
| `categoria` só é permitida em `saida` | 422 |
| A categoria informada deve existir | 422 |
| O ano não pode estar arquivado | 409 |

O `mes` não é aceito do cliente: é derivado de `data.month`.

As mesmas regras de coerência valem em atualizações parciais (`PATCH`), e são
verificadas sobre o objeto já mesclado — um PATCH que muda só o tipo pode
invalidar um `destino` que era válido antes.

### Categorias

- O nome é único.
- Excluir uma categoria **em uso** apenas a desativa (`ativa = false`); os
  lançamentos históricos e seus relatórios permanecem intactos.
- Excluir uma categoria **sem uso** a remove de fato.

### Anos

- O ano é único.
- Arquivar um ano:
  1. marca-o como somente-leitura;
  2. prepara o ano seguinte com os saldos de fechamento como abertura:
     - se ele **não existe**, é criado;
     - se existe e **ainda não tem lançamentos**, seus saldos de abertura são
       atualizados — eram placeholders zerados de um ano criado
       antecipadamente para planejamento;
     - se existe e **já tem lançamentos**, é preservado intacto.
- Um ano arquivado continua totalmente legível; qualquer escrita retorna 409.
- Desarquivar reverte o estado, mas **não** recalcula os saldos de abertura do
  ano seguinte. Se houver edição após desarquivar, ajuste-os manualmente.

### Gastos fixos

- São modelos: não movimentam dinheiro por si só.
- `pagar` gera um lançamento de `saida` na data de vencimento e marca o mês como
  pago. É **idempotente**: chamar duas vezes devolve o mesmo lançamento em vez
  de duplicar.
- Se o dia de vencimento não existe no mês (dia 31 em fevereiro), usa-se o
  último dia do mês.
- `desfazer` remove o lançamento gerado e volta a situação para pendente.
- Excluir o gasto fixo **não** remove os lançamentos já gerados: eles
  representam dinheiro que de fato saiu da conta.

### Wishlist

- Não afeta saldo nem guardado.
- O total considera apenas itens marcados (`somar = true`) e não comprados.

## Tratamento de dados incompletos

| Situação | Comportamento | Motivo |
| --- | --- | --- |
| Saída sem categoria | Agrupada em "Sem categoria" | Sumir do relatório esconderia gasto real |
| Rendimento sem destino no cálculo | Tratado como conta | Um dado incompleto não deve desaparecer do saldo |
| Mês sem lançamentos | Carrega o saldo anterior adiante | Zerar quebraria o encadeamento |
| Importação: linha sem data | Assume o dia 1º do mês | Descartar perderia dinheiro real |
| Importação: tipo desconhecido | Ignorada **e reportada** | Melhor recusar explicitamente do que adivinhar |
