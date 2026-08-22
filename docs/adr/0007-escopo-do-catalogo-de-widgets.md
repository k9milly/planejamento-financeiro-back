# ADR-0007 — O catálogo de widgets v1 usa só dados que já existem; orçamento/meta, dívidas e investimentos como entidades próprias ficam de fora

**Status:** proposto

## Contexto

A imagem de referência mostra blocos que se dividem em dois grupos bem
diferentes:

1. **Blocos que já são um dado que o sistema calcula hoje**, só que
   mostrado de um jeito novo: saldo, patrimônio, saldo por conta, gastos
   por categoria, calendário de vencimentos, lista de lançamentos,
   contas recorrentes.
2. **Blocos que dependem de um conceito que não existe no modelo de dados
   atual**: toda tabela da imagem que tem uma coluna "Meta" ou
   "Orçamento" ao lado de "Real" (Receita, Despesas, Contas Recorrentes,
   Dívidas, Investimentos) pressupõe que o usuário definiu, com
   antecedência, quanto **pretendia** gastar/receber em cada categoria —
   um orçamento. O sistema hoje só sabe o que **de fato** aconteceu
   (lançamentos). "Dívidas" e "Investimentos" como listas com suas
   próprias linhas (não só a reserva "guardado" que já existe) também são
   conceitos que não existem — o mais próximo que há hoje é o `guardado`
   por conta, que é uma aproximação grosseira de "investimento" e nenhuma
   de "dívida".

## Decisão

O catálogo de widgets do modo painel (v1) cobre só o primeiro grupo — a
lista completa, widget a widget, com a origem de cada dado, está na spec
"Modo painel: alternância, canvas infinito e catálogo de widgets". Onde a imagem
mostra "Meta"/"Orçamento", o widget correspondente nasce **sem** essa
coluna (mostra só o valor real), e onde a imagem mostra "Dívidas" ou
"Investimentos" como tabela detalhada, o widget equivalente vira algo mais
simples e honesto com o que existe hoje (ex.: total guardado por conta, no
lugar de uma lista de investimentos com aporte/rendimento individual por
linha).

## Por que separar, em vez de desenhar o orçamento/dívidas/investimentos junto

São duas decisões de produto independentes, mesmo que a imagem as mostre
juntas: **como a informação é exibida** (o pedido desta rodada) e **que
informação o sistema rastreia** (uma mudança de domínio, do mesmo porte
das que motivaram os ADRs 0001–0003 da rodada anterior). Resolver as duas
de uma vez faria esta rodada de specs crescer para muito além do que foi
pedido — o usuário pode querer o modo painel e a grade customizável sem
necessariamente querer redesenhar como o app trata metas, dívidas e
investimentos, e vice-versa. Manter as duas decisões separadas também
significa que cada uma pode ser aprovada, implementada e revertida
independentemente da outra.

## Consequências

- Alguns widgets do v1 são visualmente mais simples que o bloco
  correspondente na imagem (sem coluna de meta, sem barra de progresso
  "gasto vs. orçado"). Isso é esperado e documentado na spec, não uma
  omissão.
- Se/quando um orçamento por categoria for pedido, ele é um ADR e uma
  spec à parte (schema novo: algo como `MetaCategoria(categoria_id, ano_id,
  mes, valor_previsto)`), e os widgets afetados ganham a coluna que falta
  sem precisar mudar o motor de grade nem o catálogo em si — é uma
  extensão aditiva do widget, não uma mudança de arquitetura.
- O mesmo vale para dívidas e investimentos como entidades: quando
  pedidos, entram como um `TipoConta` novo ou um modelo próprio (a decidir
  no momento, seguindo o mesmo raciocínio do ADR-0002 da rodada anterior),
  e ganham widget dedicado depois.

## Alternativas consideradas

- **Implementar um orçamento simplificado (um valor fixo por categoria,
  sem histórico mês a mês) só para preencher as colunas "Meta" da
  imagem.** Rejeitada: mesmo "simplificado", é modelo de dados novo,
  migração nova, tela de cadastro nova — o oposto de simplificado do
  ponto de vista de escopo desta rodada, que é sobre interface.
- **Não construir os widgets do grupo 2 de jeito nenhum, nem a versão
  simplificada.** Rejeitada: deixaria o modo painel visivelmente mais
  pobre que a referência sem necessidade — a versão simplificada (dado
  real, sem meta) entrega a maior parte do valor visual do pedido sem
  exigir o domínio novo.
