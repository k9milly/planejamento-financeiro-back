# Plano de implementação — forma de pagamento, cartões e saldo inteligente

Referência: ADRs em `docs/adr/0001` a `0003`, spec detalhada em
`docs/specs/pagamentos-e-cartoes.md`. Este documento é só a **ordem** e o
**porquê** dessa ordem — não repete o detalhe técnico de cada mudança.

A ideia geral: cada fase entrega algo que já funciona sozinho (é
mergeável, testável, não deixa o app quebrado no meio do caminho), e a fase
seguinte só começa a fazer sentido depois que a anterior existe.

---

## Fase 0 — Migração de schema (aditiva, sem mudar comportamento)

**O quê:** uma migração Alembic só, criando todas as colunas/tabelas novas
das quatro mudanças de uma vez — `contas.tipo`, `contas.dia_vencimento_fatura`,
`contas.conta_pagamento_padrao_id`, `lancamentos.forma_pagamento`,
`gastos_fixos.forma_pagamento` (+ rename do texto livre para
`forma_pagamento_legado`), e a tabela `faturas_mensais`. Tudo nullable ou
com default que preserva o comportamento atual (`tipo=corrente` para toda
conta existente).

**Por quê primeiro e tudo junto:** o projeto já decidiu (ver
`docs/ARQUITETURA.md`, "Por que Alembic") que o schema nunca muda sozinho ao
subir a aplicação — migração é sempre um passo explícito e travado. Fazer
uma migração por fase geraria quatro deploys de banco em vez de um, sem
necessidade: nenhuma dessas colunas quebra nada em quem ainda não as usa.
Juntar numa só reduz o número de vezes que o banco de produção é tocado.

**Critério de saída:** `alembic upgrade head` roda limpo sobre uma cópia do
banco atual; a aplicação sobe e se comporta exatamente como antes (nenhuma
tela nova ainda lê os campos novos).

---

## Fase 1 — Tipo de conta + CRUD de cartão de crédito

**O quê:** `TipoConta`, os três campos novos em `Conta` fazendo algo (hoje
só existem no banco), validação de coerência em `ContaCriar`/`ContaAtualizar`,
filtro `?tipo=` em `GET /contas`, e a tela `GerenciadorContas.tsx` separando
"Contas" de "Cartões de crédito".

**Por quê nesta ordem:** é a fundação — nem "forma de pagamento crédito"
nem "fatura" fazem sentido se não existir, no banco, ao menos a
possibilidade de cadastrar um cartão. É também a fase que responde
diretamente ao pedido 3 ("criar uma forma de adicionar contas"): como
`Conta` já tem CRUD completo, aqui é onde ele ganha o `tipo` que faltava —
sem essa fase, item 3 já estaria tecnicamente atendido pelo que já existe,
mas sem conseguir representar um cartão.

**Depende de:** Fase 0 (schema).

**Critério de saída:** dá para criar, editar e desativar um cartão de
crédito pela tela, com dia de vencimento e conta pagadora padrão — mesmo
que nada ainda gere lançamento nele.

---

## Fase 2 — Forma de pagamento no lançamento

**O quê:** `FormaPagamento`, coluna em `Lancamento`, regra de coerência
completa (crédito exige conta-cartão; débito/pix/dinheiro exige conta
corrente), `FormularioLancamento.tsx` com o seletor novo e o filtro de
conta por tipo, coluna/badge em `TabelaLancamentos.tsx`, campo opcional na
revisão de importação de extrato.

**Por quê depois da Fase 1, e não antes:** a validação central desta fase
("crédito só em conta-cartão") não tem como existir sem que contas-cartão
já possam existir — depender da Fase 1 é literal, não só de conveniência.
É também o núcleo de onde vem o dado que alimenta a Fase 3: sem lançamento
carregando forma de pagamento e apontando pra conta certa, não há o que
"saldo inteligente" calcular de diferente do que já calcula hoje.

**Depende de:** Fase 1 (precisa de conta-cartão para validar contra).

**Critério de saída:** registrar uma saída no crédito grava normalmente,
mas (ainda nesta fase, antes da Fase 3) o saldo da conta-cartão só aparece
misturado em `por_conta` como qualquer outra conta — o comportamento visual
"saldo inteligente" só chega na próxima fase. Isso é aceitável como estado
intermediário porque a Fase 2 sozinha já é útil (o dado passa a existir e
ser válido) mesmo sem o cálculo terminado.

---

## Fase 3 — Saldo inteligente

**O quê:** separar `por_conta`/`por_cartao` em `services/calculos.py`,
propagar em `ResumoMesOut`/`ResumoAnoOut`, ajustar `TotaisMes.tsx` e o
"Patrimônio" de `GerenciadorContas.tsx` para excluir cartões da soma de
saldo disponível.

**Por quê só agora:** é onde o resultado visível do pedido 2 aparece — mas
só pode ser implementada depois que lançamentos no crédito já são gravados
apontando corretamente para a conta-cartão (Fase 2). Fazer o cálculo antes
não teria o que separar: ainda não existiria a distinção "conta vs. cartão"
nos dados.

**Depende de:** Fase 2 (lançamentos precisam já rotear crédito para o
cartão certo).

**Critério de saída:** uma saída no crédito não muda o saldo disponível
mostrado; ela aparece separadamente como dívida do cartão. Teste dedicado
em `test_calculos.py`, no espírito de `test_centavos_nao_acumulam_erro` já
existente — algo como `test_credito_nao_desconta_saldo_da_conta`.

---

## Fase 4 — Fatura do cartão: vencimento, pagamento e lembrete no calendário

**O quê:** `FaturaMensal`, `routers/faturas.py` (`pagar`/`desfazer`,
molde de `gastos_fixos.py`), exibição da fatura em aberto + botão de pagar
em `GerenciadorContas.tsx`, e o marcador de vencimento em
`CalendarioVencimentos.tsx`.

**Por quê por último entre as quatro mudanças originais:** "quanto devo" só
é um número confiável depois que compras no crédito já estão sendo
corretamente acumuladas na conta-cartão em vez de descontar da conta real
(Fase 3) — implementar o pagamento de fatura antes disso pagaria um valor
que ainda estaria sendo calculado errado (misturado com saldo comum). É
também a fase que fecha o ciclo do "saldo inteligente": o botão de pagar é
o único lugar em que dinheiro de verdade sai da conta real por causa de uma
compra no crédito, exatamente como pedido ("mostrando a data de
vencimento, campo editável, e que mostre no calendário um lembrete").

**Depende de:** Fase 3 (o valor da fatura precisa estar correto antes de
poder ser pago).

**Critério de saída:** os 4 itens pedidos pelo usuário estão todos
implementados e visíveis na interface. Pagar a fatura desconta a conta
pagadora e zera (ou reduz) a dívida do cartão; o calendário mostra o
vencimento de cada cartão ativo, com lembrete visual.

---

## Fase 5 — Gasto fixo consciente de forma de pagamento e cartão

**O quê:** `GastoFixo.forma_pagamento` (enum) + `conta_id` podendo apontar
para um cartão, migração do texto livre para `forma_pagamento_legado`,
`GastosFixos.tsx` com o mesmo seletor do formulário de lançamento.

**Por quê separada das fases 2–4, e por último:** um gasto fixo pago no
crédito (ex.: assinatura de streaming) só faz sentido depois que "pagar no
crédito" já é um conceito totalmente funcional de ponta a ponta (Fase 4) —
inclusive o pagamento da fatura, que é quem eventualmente tira esse
dinheiro da conta real. Fazer isso antes funcionaria tecnicamente, mas
deixaria o usuário testando um caminho (gasto fixo → crédito) cujo destino
final (a fatura) ainda não existiria. Também é a mudança de menor
prioridade das cinco: nenhum dos quatro pedidos originais menciona gasto
fixo explicitamente — é uma consequência natural de ter o conceito de
crédito, não um requisito à parte.

**Depende de:** Fase 4.

**Critério de saída:** marcar um gasto fixo como pago, quando ele está
configurado para crédito, gera a saída na conta-cartão certa (não na conta
real) — e essa saída se comporta em tudo como uma saída manual equivalente.

---

## Transversal — Documentação e testes

Não é uma fase à parte; acontece dentro de cada fase acima, não no fim:

- `docs/REGRAS.md` ganha as novas seções (forma de pagamento, tipos de
  conta, fatura) à medida que cada regra entra em vigor — é a referência
  que hoje já lista as regras existentes uma a uma, com o teste
  correspondente.
- `docs/ARQUITETURA.md` ganha uma entrada em "Decisões" resumindo o link
  para os ADRs 0001–0003 (o documento já aponta para decisões maiores como
  essa, ele não deveria crescer com o detalhe completo — isso fica nos
  ADRs).
- `docs/API.md` é atualizado por fase, junto com o endpoint que motivou a
  mudança.
- `frontend/src/types/api.ts` é atualizado no mesmo commit que o schema
  correspondente do backend — é a convenção já documentada em
  `ARQUITETURA.md` ("os tipos TypeScript são escritos à mão").
- Testes: cada fase adiciona os seus (`test_calculos.py` para regra de
  cálculo pura, `test_api.py` para o comportamento HTTP fim a fim,
  seguindo o padrão que já existe para gastos fixos e transferências).

## Resumo da ordem e por quê, em uma linha cada

1. **Schema** — porque o projeto não migra banco silenciosamente.
2. **Tipo de conta / cartão** — porque nada mais tem onde apontar sem isso.
3. **Forma de pagamento no lançamento** — porque depende de cartão existir
   para validar contra, e é quem produz o dado da fase seguinte.
4. **Saldo inteligente** — porque só pode separar saldo de dívida depois
   que os lançamentos já carregam essa informação corretamente.
5. **Fatura (vencimento, pagar, calendário)** — porque só faz sentido pagar
   um valor que já está sendo calculado certo.
6. **Gasto fixo consciente de crédito** — porque é a menor prioridade e
   depende do ciclo completo (compra → fatura → pagamento) já existir.
