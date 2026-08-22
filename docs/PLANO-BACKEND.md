# Plano de implementação — só backend

Este documento é a versão do trabalho recortada para uma conversa que só
vai mexer em `backend/`. Não assume que a conversa de frontend existe ou
está andando junto — cada fase abaixo termina num estado em que a API
responde corretamente e pode ser testada por conta própria (`curl`,
`/docs` do Swagger, `pytest`), sem depender de nenhuma tela nova existir.

**Contrato a entregar:** `docs/CONTRATO-API.md` — é o documento que a
conversa de frontend vai assumir como verdade. Qualquer decisão tomada
durante a implementação que mude um campo, um enum ou uma resposta em
relação ao que está lá precisa **atualizar o contrato**, não só o código —
senão o frontend implementa contra uma versão desatualizada sem saber.

**Referência de arquitetura:** ADRs `0001`, `0002`, `0003` (forma de
pagamento, cartão como tipo de conta, fatura mensal) e a metade backend do
`0006` (persistência do layout — a coluna e os dois endpoints; a UX de
quando salvar é decisão do frontend). Specs: `docs/specs/pagamentos-e-cartoes.md`
(detalhe completo de modelo/validação/endpoints) e a seção 2
("Carregamento e persistência") de `docs/specs/modo-estatico-e-widgets.md`
só para saber o formato esperado do campo `layout` (uma string opaca —
o backend não precisa entender o que tem dentro).

---

## Fase 1 — Migração de schema

**O quê:** uma migração Alembic aditiva com tudo de uma vez: `contas.tipo`,
`contas.dia_vencimento_fatura`, `contas.conta_pagamento_padrao_id`,
`lancamentos.forma_pagamento`, rename de `gastos_fixos.forma_pagamento` →
`forma_pagamento_legado` + nova `gastos_fixos.forma_pagamento`, tabela
`faturas_mensais`, e `usuarios.layout_dashboard` (texto, nullable). Todas
nullable ou com default que preserva o comportamento atual.

**Por quê tudo junto:** o projeto já decidiu (`docs/ARQUITETURA.md`, "Por
que Alembic") que o schema muda em um passo explícito, nunca sozinho ao
subir. Uma migração por fase geraria mais toques no banco de produção do
que o necessário — nenhuma dessas colunas quebra quem ainda não as usa.

**Critério de saída:** `alembic upgrade head` roda limpo; a aplicação sobe
e se comporta exatamente como antes.

---

## Fase 2 — Tipo de conta / cartão de crédito

**O quê:** `TipoConta`, os campos novos de `Conta` fazendo algo de verdade
(validação cruzada em `ContaCriar`/`ContaAtualizar`: cartão exige
`dia_vencimento_fatura`; conta corrente não aceita os campos de cartão),
filtro `?tipo=` em `GET /contas`.

**Por quê nesta ordem:** é a fundação — a validação de "crédito exige
conta-cartão" (Fase 3) não tem como existir sem que cartão já seja um
`tipo` válido de `Conta`.

**Depende de:** Fase 1.

**Critério de saída:** `POST /contas` cria um cartão com
`tipo=cartao_credito` e `dia_vencimento_fatura`; rejeita um cartão sem
vencimento (422); `GET /contas?tipo=cartao_credito` devolve só cartões.

---

## Fase 3 — Forma de pagamento no lançamento

**O quê:** `FormaPagamento`, coluna em `Lancamento`, `validar_coerencia`
estendida (recebe o `tipo` da conta, não só o id — os três chamadores,
`LancamentoBase.model_validator`, `routers/lancamentos.py::atualizar`,
`routers/importacao.py::confirmar`, precisam resolver a `Conta` antes de
validar). `TransacaoConfirmar` (importação) e `GastoFixoCriar/Atualizar`
ganham o campo.

**Por quê depois da Fase 2:** a regra central desta fase (crédito só em
conta-cartão) só pode ser escrita depois que conta-cartão existe para
validar contra.

**Depende de:** Fase 2.

**Critério de saída:** `POST /anos/{ano}/lancamentos` com
`tipo=saida, forma_pagamento=credito` e uma conta corrente devolve 422;
com uma conta-cartão, cria normalmente. Lançamentos antigos (sem o campo)
continuam passando pela validação sem quebrar.

---

## Fase 4 — Saldo inteligente

**O quê:** separar `por_conta` (só `corrente`) de `por_cartao` (só
`cartao_credito`) dentro de `services/calculos.py` — `TotaisMes` ganha
`por_cartao: dict[int, Carteiras]`, calculado a partir do `tipo` de cada
conta envolvida. `ResumoMesOut`/`ResumoAnoOut` propagam o campo novo.

**Por quê só agora:** só pode separar corretamente depois que lançamentos
já carregam `forma_pagamento` e apontam pra conta certa (Fase 3) — antes
disso não haveria o que separar.

**Depende de:** Fase 3.

**Critério de saída:** uma saída de R$100 no crédito não muda `saldo` da
conta corrente nem o agregado do mês — só aparece em `por_cartao`, como
valor negativo. Teste novo em `test_calculos.py`
(`test_credito_nao_desconta_saldo_da_conta`, no espírito do
`test_centavos_nao_acumulam_erro` já existente).

---

## Fase 5 — Fatura do cartão

**O quê:** tabela `FaturaMensal`, router `faturas.py` com os três
endpoints do contrato (`GET`, `.../pagar`, `.../desfazer`), no molde
exato de `routers/gastos_fixos.py` (idempotência incluída). O valor em
aberto é sempre recalculado a partir de `por_cartao[cartao_id].saldo` — não
é guardado em nenhum campo.

**Por quê só agora:** "quanto devo" só é confiável depois que compras no
crédito estão sendo corretamente isoladas em `por_cartao` (Fase 4) —
implementar o pagamento antes pagaria um valor calculado errado.

**Depende de:** Fase 4.

**Critério de saída:** pagar a fatura duas vezes seguidas não duplica o
lançamento; desfazer remove o lançamento e volta `pendente`; a exclusão de
uma conta-cartão com fatura paga desativa em vez de apagar (mesma regra
que já existe para conta comum, estendida para olhar `FaturaMensal`
também).

---

## Fase 6 — Gasto fixo consciente de crédito

**O quê:** `GastoFixo.conta_id` aceita apontar para uma conta-cartão;
`.../meses/{mes}/pagar` gera o lançamento com o `forma_pagamento` e
`conta_id` corretos (herdados do `GastoFixo`).

**Por quê por último entre as mudanças da primeira rodada:** um gasto fixo
pago no crédito só faz sentido de ponta a ponta depois que "pagar no
crédito" já é funcional (Fase 5, que é quem eventualmente tira o dinheiro
da conta real).

**Depende de:** Fase 5.

**Critério de saída:** marcar como pago um gasto fixo configurado para
crédito gera a saída na conta-cartão certa, não na conta real.

---

## Fase 7 — Preferência de layout do dashboard

**O quê:** coluna `Usuario.layout_dashboard` (já criada na migração da
Fase 1), os dois endpoints `GET`/`PUT /preferencias/layout-dashboard`
(novo router pequeno, registrado em `main.py` como os demais — herda a
exigência de sessão automaticamente). O conteúdo de `layout` é uma string
opaca — o backend não valida o JSON interno, só guarda e devolve.

**Por quê é independente do resto:** não depende de nenhuma das Fases
2–6 — é só uma preferência de usuário sem relação com o domínio
financeiro. Pode, na prática, ser feita a qualquer momento (inclusive em
paralelo com as outras fases, se for mais de uma pessoa mexendo no
backend); está numerada por último aqui só porque é a que motivou esta
divisão em documentos mais recentemente, não por dependência técnica.

**Depende de:** Fase 1 (só a migração, nada mais).

**Critério de saída:** `PUT /preferencias/layout-dashboard` com um JSON
qualquer, seguido de `GET`, devolve o mesmo conteúdo salvo. Um usuário
diferente não vê o layout de outro (a preferência é por `usuario_id`, não
global).

---

## Transversal — testes e documentação

Cada fase acima adiciona os testes correspondentes
(`test_calculos.py` para regra pura, `test_api.py` para comportamento
HTTP fim a fim) e atualiza `docs/REGRAS.md`/`docs/API.md` no mesmo commit
que a mudança que motivou — não no fim. `docs/ARQUITETURA.md` ganha uma
entrada apontando para os ADRs relevantes quando a decisão for
implementada, não antes.

## Resumo da ordem, em uma linha cada

1. **Schema** — o projeto não migra banco silenciosamente.
2. **Tipo de conta/cartão** — nada mais tem onde apontar sem isso.
3. **Forma de pagamento** — depende de cartão existir para validar contra.
4. **Saldo inteligente** — só separa saldo de dívida depois que os
   lançamentos já carregam o dado certo.
5. **Fatura** — só faz sentido pagar um valor já calculado certo.
6. **Gasto fixo + crédito** — menor prioridade, depende do ciclo completo.
7. **Layout do dashboard** — independente, cabe em qualquer momento após
   a Fase 1.
