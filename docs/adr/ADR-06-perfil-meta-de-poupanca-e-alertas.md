# ADR-06 — Perfil real: nome, meta de poupança e alertas de vencimento

**Status:** aceito

## Contexto

Desde a Parte 1 original deste pacote (`especificacao-tecnica-funcional.md`,
seções 6 e 7), estava documentado que **nome**, **meta de poupança** e
**alertas** não tinham nenhum suporte no backend — `GET /auth/eu` devolve só
`id` e `email`. A recomendação daquele momento foi reduzir a tela de Perfil
ao que a API sustenta (só e-mail, somente leitura) em vez de manter campos
que pareciam funcionar sem funcionar de verdade — e isso já foi
implementado (Fase 7 de `PLANO-FRONTEND.md`). A tela `/metas` (seção 7 da
Parte 1) ficou na mesma situação, por um motivo adicional: ela mistura dois
conceitos diferentes — **orçamento por categoria** (`budgets`, limite fixo
por categoria) e **meta de poupança** (`goals`, valor-alvo vs. guardado).
Orçamento por categoria já tinha sido explicitamente descartado do escopo
pelo `ADR-0007` do repositório back (o sistema só rastreia o que aconteceu,
não o que era planejado gastar) — essa parte continua fora de escopo, sem
mudança nenhuma neste ADR.

A Kamilly pediu para tirar nome, meta de poupança e alertas do estado de
"mock reduzido" e torná-los reais. Três decisões de produto precisavam ser
tomadas antes de desenhar endpoint ou tela, porque cada uma tinha mais de
um formato razoável:

1. **Formato da meta de poupança** — um valor mensal recorrente (comparado
   contra o `guardado` de cada mês, que já existe no sistema), um valor
   único com prazo (acumulando `guardado` até uma data), ou os dois.
2. **O que dispara um alerta** — vencimento de gasto fixo/fatura perto de
   vencer e ainda não pago, progresso da meta de poupança abaixo do
   esperado, saldo baixo numa conta — ou alguma combinação.
3. **Como o alerta chega até a pessoa** — só dentro do próprio app (sem
   infraestrutura nova) ou também por e-mail (que exige adicionar um
   serviço de envio de e-mail ao backend, algo que não existe hoje no
   projeto).

Essas três perguntas foram feitas diretamente à Kamilly antes deste ADR. As
respostas dela definem a decisão abaixo.

## Decisão

### 1. Nome

Campo simples: `Usuario.nome` (string, opcional). `GET /auth/eu` passa a
devolver `nome` junto com `id`/`email`; um `PATCH /auth/eu` novo permite
editar. Sem complexidade adicional — é só preencher o gap mais simples dos
três.

### 2. Meta de poupança — as duas formas, entidade própria

A Kamilly escolheu manter as duas formas (meta mensal recorrente **e** meta
única com prazo), deixando a pessoa escolher qual criar. Isso vira uma
entidade nova, não um campo solto no usuário — porque tem ciclo de vida
próprio (criar, ficar ativa, ser substituída):

```
MetaPoupanca
  id
  tipo: "mensal" | "prazo"
  valor_alvo: Decimal
  data_alvo: date | null       # obrigatório quando tipo="prazo", ignorado quando "mensal"
  criada_em: datetime
  ativa: boolean
```

Regra de negócio: no máximo **uma meta ativa por tipo** ao mesmo tempo — ou
seja, dá para ter uma meta mensal ativa e uma meta com prazo ativa ao mesmo
tempo (não são mutuamente exclusivas), mas não duas metas mensais ativas
simultaneamente. Criar uma meta nova do mesmo tipo desativa a anterior
automaticamente (histórico continua no banco, só não conta mais pro
progresso).

O progresso **não é calculado no frontend** — o backend devolve o valor já
calculado junto com a meta (reaproveitando a mesma agregação de `guardado`
que `GET /anos/{ano}/resumo` já faz), para não duplicar essa lógica em dois
lugares e arriscar os dois desencontrarem:

```
GET /metas-poupanca/ativas
→ {
    mensal: { id, valor_alvo, guardado_no_mes: Decimal, percentual: number } | null,
    prazo: { id, valor_alvo, data_alvo, guardado_acumulado: Decimal, percentual: number } | null
  }
```

Essa entidade passa a ser a implementação real do que a seção 7 da Parte 1
chamava de `goals` na tela `/metas` — **a lista de `budgets` (orçamento por
categoria) da mesma tela continua fora de escopo**, sem mudança em relação
ao que o ADR-0007 já decidiu.

### 3. Alertas — só vencimento, calculado sob demanda

A Kamilly escolheu o escopo mais estreito: só alerta de gasto fixo/fatura
perto do vencimento e ainda não pago. Progresso de meta e saldo baixo
ficam de fora por enquanto — podem virar pauta de um ADR futuro se um dia
forem desejados, mas não entram nesta rodada.

Não é uma tabela de alertas persistida — é uma consulta computada em cima
de dados que já existem (`GastoFixo.dia_vencimento`,
`Conta.dia_vencimento_fatura`, e o status pago/pendente que já é derivado
de existir ou não um `Lancamento` correspondente no mês):

```
GET /alertas
→ [
    { tipo: "gasto_fixo", gasto_fixo_id, nome, dia_vencimento, dias_restantes },
    { tipo: "fatura", cartao_id, nome_cartao, dia_vencimento_fatura, dias_restantes }
  ]
```

Só entram itens **não pagos** com vencimento dentro de uma janela fixa —
**3 dias** de antecedência para esta primeira versão (constante no backend,
não configurável pela pessoa ainda; virar configurável é uma extensão
pequena e futura, não vale complicar o v1 por isso).

### 4. Entrega — no app sempre, e-mail como opção configurável

Dentro do app: o resultado de `GET /alertas` alimenta um painel/lista na
interface — sem infraestrutura nova, é só mais uma chamada de API.

Por e-mail: opcional, configurável pela pessoa. Campo novo
`Usuario.alertas_email_ativo` (boolean, padrão `false`), com um toggle na
aba Configurações. **Isso é uma peça de infraestrutura genuinamente nova**
— precisa de (a) um serviço de envio de e-mail (o backend não manda e-mail
hoje, de nenhuma forma) e (b) alguma coisa que rode periodicamente para
checar vencimentos e disparar o envio (o backend é uma API request/response
comum, não tem hoje nenhum processo agendado rodando). Por isso o e-mail
fica como uma fase separada e posterior no plano do backend — o toggle só
deve aparecer na interface do front depois que o backend sustentar de
verdade a preferência, para não repetir o erro que a seção 6 da Parte 1 já
tinha identificado (mostrar controle que não faz nada de verdade).

## Consequências

- Uma migração nova no backend: `Usuario.nome`, `Usuario.alertas_email_ativo`,
  tabela `MetaPoupanca`.
- Endpoints novos: `PATCH /auth/eu` (nome), `GET`/`POST /metas-poupanca`,
  `GET /metas-poupanca/ativas`, `GET /alertas`. Nomes exatos de rota a
  confirmar contra a convenção que o backend já usa nos outros routers.
- A tela de Perfil (Configurações) volta a mostrar nome (editável) e ganha
  a meta de poupança com progresso real. A tela `/metas` passa a usar a
  mesma entidade `MetaPoupanca` para a parte de "goals" — a parte de
  "budgets" (orçamento por categoria) continua com o aviso de "fora de
  escopo" que a Fase 8 do `PLANO-FRONTEND.md` já registrou, sem mudança.
- Uma tela/painel novo de alertas de vencimento no front, alimentado por
  `GET /alertas`.
- O envio de e-mail é fase separada e posterior — decisão de provedor de
  e-mail (serviço transacional vs. SMTP próprio) e de mecanismo de
  agendamento (processo próprio no backend, ex. APScheduler, vs. algo
  externo) ainda em aberto, a ser resolvida quando essa fase começar; não
  bloqueia nome, meta de poupança nem os alertas dentro do app.

## Alternativas consideradas

- **Manter tudo mock, só com aviso visual** — era a decisão registrada até
  agora (Fases 7 e 8 do `PLANO-FRONTEND.md`); descartada porque a Kamilly
  pediu explicitamente para tornar isso real.
- **Meta de poupança em um formato só** — descartada; a Kamilly preferiu
  manter as duas formas (mensal recorrente e com prazo).
- **Alertas cobrindo também progresso de meta e saldo baixo** —
  descartada por enquanto, para manter o escopo desta rodada pequeno; pode
  virar pauta de um ADR futuro.
- **E-mail obrigatório desde já (sem toggle)** — descartada; a Kamilly
  pediu que fosse opcional, configurável na tela de Configurações.
