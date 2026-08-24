# Plano de implementação — só frontend

Versão do trabalho recortada para uma conversa que só vai mexer em
`frontend/`. Assume o backend como uma **caixa preta que obedece**
`docs/CONTRATO-API.md` — esta conversa não precisa ler models.py,
schemas.py nem nenhum router pra saber o que construir; o contrato já tem
tudo isso traduzido.

**Referência de arquitetura:** ADRs `0004`, `0008`, `0007` (dois modos,
canvas infinito, escopo do catálogo de widgets) e a metade frontend do
`0006` (quando salvar, o que fica local vs. servidor). O `0005` está
superado pelo `0008` — ver a nota no topo dele; não implemente
`react-grid-layout`, ele não faz mais parte do plano. Specs:
`docs/specs/modo-painel-e-widgets.md` (completa — a seção 2 foi
reescrita para o canvas infinito) e as seções "Telas afetadas" de
`docs/specs/pagamentos-e-cartoes.md` (1, 2, 3 e 4) — que é onde está o
detalhe de cada componente a mudar.

> **Atualização desta rodada:** o pedido original de "blocos ajustáveis"
> foi esclarecido para "canvas infinito, estilo planilha, sem limite de
> área" — diferente do que as Fases 7 e 8 abaixo descreviam originalmente
> (uma grade responsiva via `react-grid-layout`). Elas foram reescritas
> para refletir o ADR-0008. Nenhuma outra fase muda, e nada em
> `docs/CONTRATO-API.md`/`docs/PLANO-BACKEND-pagamentos-e-painel.md` muda — a correção é
> inteiramente frontend (o layout sempre foi uma string opaca do ponto de
> vista do backend).

## Como trabalhar sem esperar o backend terminar

O `frontend/src/lib/api.ts` já concentra **toda** chamada HTTP num único
módulo — nenhum componente chama `fetch` direto. Isso significa que dá pra
desenvolver a interface inteira contra dados falsos, trocando só esse
módulo, sem esperar o backend implementar `docs/CONTRATO-API.md` de
verdade:

1. Um arquivo novo, `frontend/src/lib/dadosFalsos.ts`, com objetos que
   seguem exatamente os tipos do contrato (`ContaOut` com `tipo=cartao_credito`,
   um `ResumoMesOut` com `por_cartao` preenchido, etc.).
2. Uma flag (`VITE_API_FALSA=1` no `.env.local`, por exemplo) que faz
   `api.ts` devolver os dados falsos em vez de chamar `fetch`, só nas
   funções que dependem de endpoints ainda não implementados.
3. Quando o backend entregar de verdade (ou já tiver entregue — ver
   `docs/PLANO-BACKEND-pagamentos-e-painel.md`), a flag sai e tudo passa a bater no servidor
   real, sem mudar nenhum componente — eles já foram escritos contra os
   tipos do contrato, não contra o mock.

Isso é opcional — se as duas conversas forem rodar em sequência (backend
primeiro, depois frontend), não é necessário, o frontend já acha a API de
verdade no ar. É útil se as duas forem rodar **em paralelo**.

---

## Fase 1 — Extrair `ModoPlanilha`, sem mudar comportamento

**O quê:** mover o corpo atual de `App.tsx` para `ModoPlanilha.tsx`
(cópia mecânica, sem lógica nova), deixar `App.tsx` só com a busca de
dados e a escolha de modo (por enquanto sempre `planilha`).

**Por quê primeiro:** risco baixo, sem dependência de nada do contrato —
não toca em nenhum endpoint novo. É pré-requisito estrutural de tudo que
vem depois (tanto o modo painel quanto qualquer tela que precise saber
filtrar conta por tipo).

**Depende de:** nada (não depende do backend estar pronto).

**Critério de saída:** app se comporta exatamente como hoje.

---

## Fase 2 — Telas de forma de pagamento

**O quê:** `FormularioLancamento.tsx` (select de forma de pagamento,
visível só em `tipo=saida`; filtro do select de conta por `tipo`
compatível — ver tabela no `CONTRATO-API.md`), `TabelaLancamentos.tsx`
(badge da forma de pagamento), `ImportarExtrato.tsx` (campo opcional na
revisão), `GastosFixos.tsx` (mesmo select).

**Por quê nesta ordem:** é a mudança de UI mais isolada e mais usada (toda
saída passa por ela) — vale validar cedo, inclusive contra dados falsos
(ver seção acima), já que não depende de nenhuma outra tela nova, só do
contrato de `Lancamento`/`GastoFixo`.

**Depende de:** Fase 1. Do contrato: `Lancamento.forma_pagamento`,
`GastoFixo.forma_pagamento`, `Conta.tipo`.

**Critério de saída:** escolher "crédito" no formulário troca o que
aparece no select de conta para só cartões; as demais opções mostram só
contas correntes.

---

## Fase 3 — `GerenciadorContas.tsx` com cartões

**O quê:** formulário de "+ Nova" ganha o seletor Conta/Cartão, campos de
`dia_vencimento_fatura` e `conta_pagamento_padrao_id` quando cartão é
escolhido; lista passa a ter duas seções (Contas / Cartões de crédito);
patrimônio exibido soma só `por_conta`.

**Por quê depois da Fase 2:** reaproveita o mesmo entendimento de
"conta vs. cartão" que a Fase 2 já deixou modelado no frontend
(`types/api.ts` com `TipoConta`).

**Depende de:** Fase 2. Do contrato: `Conta.tipo`,
`dia_vencimento_fatura`, `conta_pagamento_padrao_id`,
`ResumoMesOut.por_cartao`.

**Critério de saída:** criar um cartão pela tela funciona; o patrimônio
mostrado não muda quando um cartão tem dívida (só a seção separada de
cartões reflete isso).

---

## Fase 4 — Saldo inteligente na interface

**O quê:** conferir que `TotaisMes.tsx` usa só `por_conta` (o backend já
filtra, ver contrato — aqui é conferência, não filtro novo do lado do
frontend), texto de apoio explicando que crédito não desconta até a
fatura ser paga.

**Por quê separada da Fase 3:** é pouco código, mas é o ponto do pedido
original ("quero ver o saldo que tem de verdade") — vale um passo
dedicado para não passar despercebido dentro da Fase 3.

**Depende de:** Fase 3.

**Critério de saída:** uma saída no crédito, registrada na Fase 2, não
muda o número de "Saldo" em destaque.

---

## Fase 5 — Fatura do cartão na interface

**O quê:** seção "Cartões de crédito" em `GerenciadorContas.tsx` ganha
fatura em aberto + "vence dia N" + botão "Marcar fatura como paga"
(mini-formulário de conta pagadora, pré-preenchido quando há
`conta_pagamento_padrao_id`); `CalendarioVencimentos.tsx` ganha o
marcador de vencimento de fatura (prop nova `cartoes`, visual distinto do
gasto fixo).

**Por quê por último entre as telas da primeira rodada:** é a tela que
fecha o ciclo visual do saldo inteligente — só faz sentido depois que a
Fase 4 já garante que o número "em aberto" que ela mostra é consistente
com o resto da tela.

**Depende de:** Fase 4. Do contrato: os três endpoints de
`/anos/{ano}/cartoes/{cartao_id}/fatura`.

**Critério de saída:** pagar a fatura pela tela reflete o saldo da conta
pagadora e a fatura em aberto do cartão imediatamente após recarregar.

---

## Fase 6 — Alternância de modo + `ModoPainel` vazio

**O quê:** `useModoVisual`, botão no cabeçalho, `ModoPainel.tsx` como
placeholder.

**Por quê só agora:** tecnicamente independente das Fases 2–5 (poderia vir
logo depois da Fase 1) — está posicionada aqui porque não há urgência em
paralelizar com o trabalho de forma de pagamento/cartão, e validar a
alternância de modo isoladamente, antes de somar a grade (Fase 7), reduz
o que pode dar errado de uma vez. Se a pessoa implementando preferir
adiantar esta fase para logo após a Fase 1, não há dependência técnica
que impeça.

**Depende de:** Fase 1.

**Critério de saída:** alternar entre os dois modos preserva ano/mês
selecionado e persiste a escolha ao recarregar.

---

## Fase 7 — Canvas infinito, sem persistência

**O quê:** o canvas pannable dentro de `ModoPainel` (ver ADR-0008 e a
spec, seção 2): superfície movida por `transform`, grade de fundo,
`dnd-kit` para arrastar, alça própria para redimensionar, snap em
células, extensão sob demanda das bordas, virtualização (só monta widgets
visíveis), botão "Centralizar". Layout fixo de widgets fictícios só para
validar o comportamento — sem "Salvar layout", sem chamar o backend.

**Por quê separado da persistência:** isola o risco técnico do canvas
(pan, extensão sob demanda, virtualização — a parte tecnicamente mais
arriscada desta rodada) do risco de integração com a API — não depende do
contrato de `/preferencias/layout-dashboard` estar implementado de
verdade no servidor.

**Depende de:** Fase 6.

**Critério de saída:** arrastar o fundo em qualquer direção nunca esbarra
numa borda visível, inclusive para coordenadas negativas; soltar um
widget sobre outro é rejeitado (volta pra posição anterior); "Centralizar"
reenquadra os widgets de teste.

---

## Fase 8 — Persistência do layout

**O quê:** modo de edição completo ("Editar layout", "+" de adicionar,
"✕" de remover, "Salvar layout", "Restaurar padrão"), fluxo de
carregamento (servidor → local → padrão de fábrica, posicionado perto da
origem), chamadas a `GET`/`PUT /preferencias/layout-dashboard`. Inclui a
confirmação transitória de "Layout salvo" (some sozinha depois de alguns
segundos — ver spec, seção 2, "Confirmação de salvamento": é uma correção
explícita desta rodada a um comportamento que, na primeira versão desta
spec, ficava preso na tela).

**Por quê depois do canvas puro:** o schema do `ItemLayout`
(`coluna`/`linha` com sinal, `largura`/`altura` em células) só é desenhado
com confiança depois de ver o canvas funcionando de verdade (Fase 7). Pode
usar dados falsos para os dois endpoints (ver seção "Como trabalhar sem
esperar o backend") se o backend ainda não os tiver implementado.

**Depende de:** Fase 7. Do contrato: `GET`/`PUT /preferencias/layout-dashboard`.

**Critério de saída:** um layout arrastado (incluindo widgets em
coordenadas negativas) sobrevive a um F5; "Salvar layout" grava no
servidor (real ou falso) e a confirmação desaparece sozinha; "Restaurar
padrão" funciona; clicar "Salvar" várias vezes seguidas nunca deixa duas
confirmações empilhadas nem uma presa na tela.

---

## Fase 9 — Catálogo de widgets v1

**O quê:** os widgets da tabela da spec que não dependem de cartão/fatura
— saldo, patrimônio, gastos por categoria (rosca e tabela, via Recharts),
calendário (só gastos fixos por enquanto), lançamentos do mês, wishlist,
contas recorrentes, saldo inicial, despesas diárias (calculado no
cliente).

**Por quê nesta ordem:** é o grosso do valor visual pedido; não tem
dependência de contrato além do que as Fases 2–5 já cobriram
(`ResumoMesOut`, `GastoFixo[]`, `Lancamento[]`, `Desejo[]`, todos já
existentes ou já contemplados).

**Depende de:** Fase 8 (precisa de onde colocar os widgets) e da Fase 5
(o widget "contas recorrentes" e "calendário" reaproveitam o que ela já
construiu).

**Critério de saída:** o layout padrão de fábrica mostra todos os widgets
v1 com dado real e correto para o mês selecionado.

---

## Fase 10 — Widgets de fatura de cartão

**O quê:** widget "fatura de cartão em aberto" e o marcador de fatura
dentro do widget de calendário do modo painel.

**Por quê por último:** depende de `por_cartao` e dos endpoints de fatura
(Fase 5) já estarem integrados na interface — é literalmente reaproveitar
o que a Fase 5 já buscou/calculou, só numa casca visual nova.

**Depende de:** Fase 9.

**Critério de saída:** os 2 pedidos desta rodada (alternância de modo +
blocos ajustáveis) estão implementados de ponta a ponta, com todos os
widgets do catálogo v1 (incluindo os de cartão/fatura) funcionando.

---

## Resumo da ordem, em uma linha cada

1. **Extrair `ModoPlanilha`** — pré-requisito estrutural, sem dependência.
2. **Forma de pagamento** — mudança de UI mais isolada e mais usada.
3. **Contas/cartões na tela** — reaproveita o entendimento de tipo já
   modelado na Fase 2.
4. **Saldo inteligente na interface** — o ponto central do pedido
   original, isolado pra não passar despercebido.
5. **Fatura na interface** — fecha o ciclo visual, depende da Fase 4
   estar consistente.
6. **Alternância de modo** — independente, mas sequenciada aqui para não
   competir com o trabalho de cartão/forma de pagamento.
7. **Motor de grade puro** — isola risco técnico da dependência nova.
8. **Persistência do layout** — só depois do motor funcionar de verdade.
9. **Catálogo de widgets v1** — o grosso do valor visual, sem dependência
   fora do que já foi construído.
10. **Widgets de fatura** — última peça, reaproveita a Fase 5 numa casca
    nova.
