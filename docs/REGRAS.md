# Regras de negócio

Referência das regras que o sistema aplica. Cada uma tem um teste
correspondente em `backend/tests/`.

## Carteiras

O sistema modela **duas carteiras**:

- **Conta** — dinheiro disponível para o dia a dia.
- **Guardado** — a reserva.

Todo lançamento afeta uma delas ou move dinheiro entre as duas. O patrimônio
total é `saldo + guardado_acumulado`.

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
  2. cria o ano seguinte com os saldos de fechamento como abertura, **se ele
     ainda não existir** — arquivar nunca sobrescreve dados já lançados.
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
