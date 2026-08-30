# Especificação Técnica e Funcional — Integração do frontend Lovable com o backend FastAPI

## Atualização — Etapa A concluída (paridade de domínio no mock)

Este documento foi revisado depois que a conversa do Claude Code responsável
pelo `planejamento-financeiro-front` implementou, em cima de dados mocados,
as telas que faltavam para o domínio bater com o backend: **Contas** (com
saldo/fatura mockados, dentro de Configurações, e um bloco novo no
Dashboard), **Gastos Fixos** (rota nova), **Wishlist** (rota nova),
**Calendário de Vencimentos** (componente novo, embutido no Dashboard), e
**Categorias** com CRUD de verdade. O formulário de Lançamentos também já
tem conta, forma de pagamento e os 7 tipos — as seções 2 e 3 abaixo, que
antes descreviam um gap, agora descrevem apenas o mapeamento para a API.

Cinco seções novas (8 a 11-A) cobrem as telas que não existiam quando este
documento foi escrito pela primeira vez. As seções 1–7 originais foram
mantidas, com pequenas correções onde o código real ficou diferente do que
foi só recomendado antes.

## Como este documento foi construído

Antes de mapear qualquer tela, os dois repositórios foram clonados e lidos por
completo:

- **`planejamento-financeiro-back`** — API em Python/FastAPI, já
  implementada e em produção (Fly.io, região `gru`). Não é Spring Boot/Java
  (confirmado: não há nenhum arquivo `.java`, `pom.xml` ou `build.gradle` no
  repositório) — é a mesma aplicação FastAPI que motivou os ADRs 0001–0009
  deste projeto, com todos os endpoints já funcionando: contas (com tipo
  corrente/cartão), forma de pagamento, saldo inteligente, fatura de cartão,
  categorias, gastos fixos, wishlist, importação de extrato e preferências de
  layout do painel.
- **`planejamento-financeiro-front`** — gerado no Lovable a partir de um
  prompt descritivo (ver `README.md` do repo), stack React 19 + **TanStack
  Start** (não é um SPA puro em Vite — é um framework com renderização no
  servidor, `src/server.ts`/`src/start.ts`, alvo de build `nitro`/Cloudflare)
  + Tailwind v4 + shadcn/Radix + Recharts. Hoje roda inteiramente sobre dados
  mocados em `src/lib/finance-data.ts`, sem nenhuma chamada de rede.

O achado mais importante da leitura, que molda o resto deste documento: **o
Lovable não conhecia o domínio real do app** — ele recebeu um prompt genérico
de "sistema de planejamento financeiro" e modelou uma entidade `Transaction`
simples (`receita`/`despesa`, sem conta, sem forma de pagamento, com um
campo `status: pago/pendente` que não existe no backend). O backend, por
outro lado, já carrega toda a evolução deste projeto: duas carteiras (conta e
guardado), sete tipos de lançamento, forma de pagamento, cartão de crédito
como tipo de conta, fatura mensal. Este documento existe para reconciliar as
duas coisas — tela por tela — e não apenas para "encontrar o endpoint que
bate com o mock".

Onde o mock do Lovable modela algo que o domínio real não tem (ex.: "Metas &
Orçamentos"), ou modela algo mais pobre do que o domínio real oferece (ex.:
`Lançamentos` sem seletor de conta), este documento diz isso explicitamente
em vez de forçar um mapeamento artificial — é informação que a Parte 3
(tasklists) e as ADRs precisam para decidir o que entra nesta rodada de
integração e o que fica para depois.

## Panorama — telas do frontend x domínio do backend

| Tela (Lovable) | Rota | Cobertura pelo backend hoje |
| --- | --- | --- |
| Dashboard | `/` | Total — `GET /anos/{ano}/resumo` |
| Lançamentos | `/lancamentos` | Parcial — CRUD existe, mas o modelo da tela é mais simples que `Lancamento` |
| Tabela Dinâmica | `/tabela-dinamica` | Parcial — só faz sentido para saídas (ver seção 3) |
| Mês (detalhe) | `/mes/$ano/$mes` | Total — mesmos endpoints do Dashboard e Lançamentos, filtrados por mês |
| Metas & Orçamentos | `/metas` | **Nenhuma** — conceito não existe no backend (ver ADR-0007 do repo back, que já rejeitou orçamento/meta por categoria conscientemente) |
| Configurações → Categorias | `/configuracoes` | Total — endpoints de CRUD já existem, só não são usados pela tela |
| Configurações → Perfil/Alertas | `/configuracoes` | **Nenhuma** — não existe endpoint de perfil de usuário nem de preferências de alerta |

## Pré-requisito de tudo: autenticação

Nenhuma rota de dado funciona sem login — todas exigem
`Authorization: Bearer <token>` (ver ADR-03 para a política completa).

### `POST /auth/login`

Request:

```ts
interface Credenciais {
  email: string;
  senha: string;
}
```

Response `200`:

```ts
interface TokenOut {
  token: string;
  email: string;
}
```

`401` com `{ "detail": "E-mail ou senha incorretos." }` — mesma mensagem para
e-mail inexistente e senha errada (decisão de segurança já tomada no
backend, ver `routers/auth.py`).

### `GET /auth/eu`

Header: `Authorization: Bearer <token>`. Response `200`:

```ts
interface UsuarioOut {
  id: number;
  email: string;
}
```

Usado na abertura do app para saber se o token salvo ainda vale, antes de
mostrar qualquer tela — o frontend deve chamar isto antes de renderizar
`AppShell`, não depois.

Não existe endpoint de cadastro (de propósito — ver comentário no topo de
`routers/auth.py`). O usuário é criado por script no servidor.

---

## 1. Dashboard (`/`)

### O que a tela mostra hoje (mock)

KPIs (Saldo Total, Entradas do Período, Saídas do Período, Taxa de
Poupança), um gráfico combinado (barras de entradas/saídas + linha de saldo)
por mês, uma rosca de saídas por categoria, e uma lista de lançamentos
recentes. Tudo calculado no cliente a partir do array `transactions`
completo.

### Mapeamento para a API real

Uma única chamada resolve a tela inteira: **`GET /anos/{ano}/resumo`**.

```ts
interface CarteirasContaOut {
  conta_id: number;
  nome: string;
  cor: string;
  saldo: string;     // Decimal como string — nunca `number`, ver nota abaixo
  guardado: string;
}

interface GastoCategoriaOut {
  categoria: string;
  total: string;
  percentual: number;
}

interface ResumoMesOut {
  mes: number;
  nome_mes: string;
  entradas: string;
  saidas: string;
  guardado_no_mes: string;
  saldo: string;
  saldo_inicial: string;
  guardado_acumulado: string;
  rendimentos: string;
  perdas: string;
  transferido: string;
  por_conta: CarteirasContaOut[];
  por_cartao: CarteirasContaOut[];   // fatura em aberto = -saldo
  gastos_por_categoria: GastoCategoriaOut[];
}

interface ResumoAnoOut {
  ano: number;
  arquivado: boolean;
  total_guardado: string;
  saldo_final: string;
  total_entradas: string;
  total_saidas: string;
  por_conta: CarteirasContaOut[];
  por_cartao: CarteirasContaOut[];
  meses: ResumoMesOut[];   // sempre os 12 — a tela filtra no cliente pelo mês selecionado
}
```

**Nota sobre `Decimal` como string:** todo valor monetário da API vem como
string (`"1234.56"`), não `number`. É proposital — evita erro de
arredondamento de ponto flutuante em cálculos financeiros. O ADR-01 volta a
este ponto; por ora, a regra prática: nunca fazer `JSON.parse` tratar esses
campos como número, e converter para exibição só na borda (formatação),
nunca antes de somar/comparar.

### Diferenças em relação ao mock — decisões necessárias

- **"Saldo Total" hoje é `receita - despesa` somado ingenuamente.** O
  backend já resolve isso melhor: `ResumoAnoOut.saldo_final` é o saldo real
  de fechamento, e **não inclui o que foi gasto no crédito ainda não
  pago** — é literalmente o "saldo inteligente" que motivou o ADR-0002 do
  repo back. Recomendação: o KPI "Saldo Total" deve mostrar `saldo_final`
  (ou a soma de `por_conta[].saldo`, que dá o mesmo número), não uma soma
  ingênua de lançamentos.
- **O gráfico "Entradas vs Saídas" e a rosca de categorias já têm dado
  pronto** em `ResumoMesOut` — não precisam ser recalculados no cliente a
  partir de uma lista de lançamentos crua. Isso também resolve com uma
  chamada só, em vez de buscar todos os lançamentos do ano e agregar no
  navegador.
- **Feito na Etapa A:** o Dashboard ganhou uma seção "Contas" com um card
  por conta (saldo disponível para corrente, fatura em aberto para cartão,
  nunca somados) — exatamente o que esta seção recomendava. Na integração
  real, **o valor de cada card não vem de `GET /contas`** (que não tem
  campo de saldo — ver seção 8) **e sim de `por_conta`/`por_cartao` dentro
  de `GET /anos/{ano}/resumo`**, casado pelo `conta_id`. É a mesma chamada
  que já alimenta os KPIs do topo, só lida de novo com outra chave.
- **"Lançamentos recentes"** pode continuar vindo de
  `GET /anos/{ano}/lancamentos?mes={mes}` (ver seção 2) ordenado por data,
  já que o resumo não traz a lista crua.

---

## 2. Lançamentos (`/lancamentos`)

**Feito na Etapa A:** os quatro pontos que esta seção pedia como
obrigatórios ou faseados já existem no mock — seletor de conta (filtrado
por tipo conforme a forma de pagamento, igual à regra do backend), forma de
pagamento condicional a `tipo=saida`, os 7 valores de `TipoLancamento` (não
só entrada/saída), campo "Destino" para rendimento/perda e "Conta de
destino" para transferência, e a coluna "Status" foi removida. A leitura
abaixo continua valendo — é o mapeamento desses campos, já existentes no
mock, para a API real.

### O que a tela mostra hoje (mock)

Tabela com busca, filtro por categoria/tipo/status, e um modal único de
criar/editar com campos: data, valor, descrição, categoria, tipo
(receita/despesa), status (pago/pendente).

### Mapeamento para a API real

**`GET /anos/{ano}/lancamentos`** — query params opcionais: `mes` (1–12),
`tipo`, `categoria_id`, `conta_id`. Filtro por categoria/tipo pode migrar do
cliente para a query string (menos dado trafegado); busca por texto livre
("descrição ou categoria") continua no cliente, pois a API não tem busca por
texto.

```ts
interface LancamentoOut {
  id: number;
  ano_id: number;
  mes: number;
  data: string;            // "YYYY-MM-DD"
  valor: string;           // Decimal como string
  tipo: TipoLancamento;
  conta_id: number;
  conta_destino_id: number | null;
  conta: ContaOut;
  destino: "conta" | "guardado" | null;
  categoria_id: number | null;
  categoria: CategoriaOut | null;
  forma_pagamento: "credito" | "debito" | "pix" | "dinheiro" | null;
  descricao: string;
  fitid: string | null;
}

type TipoLancamento =
  | "entrada" | "saida" | "guardado" | "retirado"
  | "rendimento" | "perda" | "transferencia";
```

**`POST /anos/{ano}/lancamentos`** — cria (`201`). **`PATCH
/anos/{ano}/lancamentos/{id}`** — edição parcial. **`DELETE
/anos/{ano}/lancamentos/{id}`** — remove.

```ts
interface LancamentoCriar {
  data: string;
  valor: string;            // > 0, obrigatório
  tipo: TipoLancamento;
  conta_id: number;
  conta_destino_id?: number | null;   // só para tipo=transferencia
  destino?: "conta" | "guardado" | null; // só para rendimento/perda
  categoria_id?: number | null;       // só para tipo=saida
  forma_pagamento?: "credito" | "debito" | "pix" | "dinheiro" | null; // só para tipo=saida
  descricao?: string;
}
```

Regras de coerência (o backend valida com `422` se violadas — o formulário
do modal precisa impedir a maioria delas antes de enviar, para não devolver
um erro genérico ao usuário):

- `categoria_id` só é aceito quando `tipo=saida`.
- `forma_pagamento` só é aceito quando `tipo=saida`; se ausente, é tratado
  como débito.
- `forma_pagamento=credito` exige que `conta_id` aponte para uma conta
  `tipo=cartao_credito`; qualquer outra forma de pagamento exige conta
  `tipo=corrente`.
- `tipo=transferencia` exige `conta_destino_id` (diferente de `conta_id`);
  nenhum outro tipo aceita `conta_destino_id`.
- `tipo` em `rendimento`/`perda` exige `destino` (`conta` ou `guardado`);
  nenhum outro tipo aceita `destino`.

### Diferenças em relação ao mock — decisões necessárias

Esta é a tela com a maior distância entre o mock e o domínio real. Quatro
pontos, em ordem de impacto:

1. **Falta seletor de conta.** Todo `Lancamento` real pertence a uma
   `Conta` — o mock não tem esse campo porque não sabia que "conta" existe.
   Sem isso, é impossível criar um lançamento de verdade. **Obrigatório**
   para esta integração, não é opcional: o modal precisa de um `<select>`
   de conta, alimentado por `GET /contas`.
2. **`status: pago/pendente` não existe em `Lancamento`.** No domínio real,
   um lançamento representa dinheiro que **já se moveu** — não há
   "lançamento pendente". O que existe com esse conceito é bem mais
   específico: `GastoFixo` (despesa recorrente, com `situacao` por mês) e
   `FaturaMensal` (fatura do cartão, com `situacao`). Recomendação: **tirar
   o campo/filtro "status" da tela de Lançamentos** nesta rodada — ele não
   tem onde gravar — e tratar "gasto fixo pendente" como uma tela/feature
   separada no futuro (o app antigo, no modo planilha, já tem exatamente
   esse widget pronto para servir de referência, se um dia for pedido aqui
   também).
3. **`type: receita/despesa` (2 valores) vs `TipoLancamento` (7
   valores).** O mock só conhece entrada/saída. O domínio real também tem
   `guardado`/`retirado` (mover para/da reserva) e `rendimento`/`perda`
   (com destino) e `transferencia` — são o coração do "saldo inteligente"
   já construído no backend. Recomendação faseada: o `<select>` de tipo do
   modal nasce com `entrada`/`saida` (mapeamento direto do que já existe na
   tela), e os demais tipos entram numa fase seguinte do plano de
   implementação (Parte 3) — não são bloqueantes para a tela funcionar, mas
   ocultá-los para sempre jogaria fora funcionalidade que o backend já
   entrega.
4. **Categoria é uma lista fixa no cliente (`CATEGORIES`), não
   `categoria_id`.** Precisa vir de `GET /categorias` (ver seção 5) e o
   formulário precisa enviar o `id`, não o nome.

---

## 3. Tabela Dinâmica (`/tabela-dinamica`)

**Feito na Etapa A:** o seletor "Saídas / Entradas" foi removido, seguindo
a recomendação desta seção — a tabela é sempre de saídas agora, com um
comentário no código (`tabela-dinamica.tsx`) explicando o porquê. A
categoria também passou a vir de `categoriaId` (via `CategoriesProvider`),
não mais de um nome fixo.

### O que a tela mostra hoje (mock)

Pivô categoria × mês, somando `transactions` no cliente, sempre sobre
saídas.

### Mapeamento para a API real

A fonte mais barata é o mesmo `GET /anos/{ano}/resumo` do Dashboard:
`ResumoMesOut.gastos_por_categoria`, por mês, já vem pronto — a tabela
dinâmica de saídas é uma transposição direta desse array, sem precisar
buscar lançamento por lançamento.

### Diferença de domínio que precisa de uma decisão de produto

**Só saídas têm categoria** — é uma regra de negócio explícita do backend
(`schemas.py`: *"Somente lançamentos do tipo saída podem ter categoria"*,
reforçada em `validar_coerencia`). Isso significa que o seletor
"Saídas / Entradas" do mock não tem, hoje, um dado equivalente do lado
"Entradas": não existe `gastos_por_categoria` para receitas, porque receitas
não têm categoria no domínio real.

Duas saídas possíveis, para decidir antes de implementar (fica registrado
aqui para a Parte 3 não implementar algo que a API não sustenta):

- **Restringir a tabela dinâmica a saídas apenas**, removendo o seletor —
  a opção mais simples e consistente com o backend hoje.
- **Categorizar entradas também** — mudança de regra de negócio no backend
  (torna `categoria_id` válido para `tipo=entrada`), fora do escopo de uma
  integração front↔back; seria um ADR e uma migração à parte, no mesmo
  espírito do que os ADRs 0001–0003 do repo back já fizeram para outras
  mudanças de domínio.

Este documento recomenda a primeira opção para esta rodada.

---

## 4. Mês — detalhe (`/mes/$ano/$mes`)

### Mapeamento para a API real

Mesmos dois endpoints das telas anteriores, filtrados pelo mês da rota:

- `GET /anos/{ano}/resumo` → pega o item de `meses[]` cujo `mes` bate com o
  parâmetro da rota, para os KPIs e o card "Saídas por categoria".
- `GET /anos/{ano}/lancamentos?mes={mes}` → alimenta a tabela de
  lançamentos do mês.

Nenhuma diferença de domínio nova além das já listadas nas seções 1 e 2 — é
a mesma informação, só filtrada. O botão "Taxa de Poupança" pode continuar
calculado no cliente (`(entradas - saidas) / entradas`) a partir do
`ResumoMesOut`, já que a API não expõe esse percentual diretamente.

---

## 5. Configurações → Categorias (`/configuracoes`)

**Feito na Etapa A:** a seção "Categorias" dentro de Configurações agora
tem criar, editar (nome, cor, ativa/inativa via `Switch`) e excluir —
exatamente o CRUD que esta seção pedia. O texto abaixo, escrito antes dessa
mudança, descreve o mapeamento; a "decisão necessária" que fechava a seção
já foi endereçada.

### O que a tela mostra hoje (mock, antes da Etapa A)

Uma lista somente-leitura de chips com os nomes fixos de `CATEGORIES` — não
tinha criar, editar nem apagar.

### Mapeamento para a API real

O backend já tem CRUD completo — a tela é que está incompleta em relação ao
que a API oferece, não o contrário:

- **`GET /categorias?incluir_inativas=false`** → lista (ativas por padrão).
- **`POST /categorias`** → cria.
- **`PATCH /categorias/{id}`** → edita.
- **`DELETE /categorias/{id}`** → apaga se não estiver em uso, senão apenas
  desativa (`ativa=false`) — categoria em uso não pode sumir dos
  lançamentos históricos.

```ts
interface CategoriaCriar {
  nome: string;    // 1–60 caracteres
  cor?: string;     // "#rrggbb", default "#94a3b8"
}
interface CategoriaAtualizar {
  nome?: string;
  cor?: string;
  ativa?: boolean;
}
interface CategoriaOut {
  id: number;
  nome: string;
  cor: string;
  ativa: boolean;
}
```

`409` se o nome já existir (`"Já existe uma categoria chamada '...'."`).

### Decisão necessária

A tela precisa ganhar formulário de criar/editar e um botão de
excluir/desativar — hoje ela é só uma vitrine. Como as demais telas
(Lançamentos, Tabela Dinâmica) passam a depender de `categoria_id` real em
vez do array `CATEGORIES` hardcoded, esta tela deixa de ser cosmética: sem
ela funcionando, não há como o usuário criar a primeira categoria própria
depois do seed inicial.

---

## 6. Configurações → Perfil e Alertas (`/configuracoes`)

**Atualização (ADR-06):** nome, meta de poupança e alertas de vencimento
deixaram de ser um gap deliberado — viraram uma decisão de produto tomada
de propósito, com contrato de API na seção 12. O texto abaixo (seções "O
que a tela mostra hoje" e "Decisão necessária") descreve a situação
**anterior** ao ADR-06, mantido aqui como registro do porquê a redução de
escopo foi a decisão certa naquele momento.

### O que a tela mostra hoje (mock)

Campos de nome, e-mail e "meta de taxa de poupança (%)" com valores
hardcoded, e dois toggles de alerta (`useState` local, sem persistência).

### O que a API oferece hoje

Nada disso tem endpoint. `GET /auth/eu` devolve só `id` e `email` — sem
nome, sem meta de poupança, sem preferências de alerta. Não existe rota de
"editar perfil".

### Decisão necessária

Não é possível fechar o gap com o que já existe — é um recorte de produto
novo, não um problema de integração. Duas opções para esta rodada:

- **Reduzir a tela ao que a API sustenta**: mostrar o e-mail (somente
  leitura, vindo de `GET /auth/eu`), remover nome/meta-poupança/alertas do
  formulário, deixando claro na interface que essas preferências ainda não
  existem no backend.
- **Manter os campos, mas sem persistência real** (continuam em estado
  local, não sobrevivem a um refresh), com uma nota visual de "em breve" —
  arriscado, porque simula uma funcionalidade que não funciona de verdade.

Este documento recomenda a primeira opção. Se meta de poupança e alertas
forem, de fato, desejados, isso é um ADR e um endpoint novo no backend (uma
tabela `PreferenciaUsuario`, no mesmo espírito de
`Usuario.layout_dashboard`), não uma tarefa de frontend.

---

## 7. Metas & Orçamentos (`/metas`)

**Atualização (ADR-06):** a parte de **meta de poupança** (`goals`) desta
tela ganhou contrato de API real — ver seção 12. A parte de **orçamento por
categoria** (`budgets`) continua fora de escopo, sem nenhuma mudança em
relação ao que está descrito abaixo e ao `ADR-0007` do repositório back.

### O que a tela mostra hoje (mock)

Duas listas com barra de progresso: orçamento por categoria (`budgets`,
limite fixo por categoria) e metas de poupança (`goals`, valor-alvo vs.
guardado), ambas com dados fixos em `finance-data.ts`.

### O que a API oferece hoje

**Nada.** Isto não é uma lacuna acidental — o repositório back já discutiu
exatamente esta funcionalidade e decidiu conscientemente deixá-la de fora
(ver `docs/adr/0007-escopo-do-catalogo-de-widgets.md` do repo back): o
sistema hoje só sabe o que **de fato** aconteceu (lançamentos), não o que o
usuário **pretendia** gastar — não existe `MetaCategoria` nem uma entidade
de meta de poupança com aporte/histórico. A aproximação mais próxima que
existe é o total `guardado` por conta, que é uma aproximação grosseira de
"investimento", não de "meta com alvo".

### Decisão necessária

Fora do escopo desta integração — mesma fronteira que o ADR-0007 já traçou
para o modo painel do outro repositório, e pelo mesmo motivo: é uma decisão
de **que informação o sistema rastreia**, independente de **como a
informação é exibida**. Recomendação: manter a tela renderizando os dados
mocados de `finance-data.ts` por enquanto, com um aviso visual de "dados de
exemplo" (não fingir que é real), ou remover o item do menu até que
orçamento/meta vire uma decisão de produto tomada de propósito, com ADR e
schema novo no backend, como qualquer outra mudança de domínio deste
projeto.

---

## 8. Contas (Configurações → Contas, e o bloco "Contas" do Dashboard)

### O que a tela mostra hoje (mock, pós-Etapa A)

Em `configuracoes.tsx`, uma seção "Contas" (`ContasSection`) com lista de
contas (nome, cor, tipo, e para cada uma: saldo disponível ou fatura em
aberto + situação pago/pendente do mês selecionado), criar/editar via
Dialog, excluir, e um botão "Pagar fatura" por cartão (Dialog próprio,
100% mock — `faturasPagas` é um `useState` local por
`${contaId}-${year}-${month}`, comentado no código como provisório). O
Dashboard (`index.tsx`) tem o bloco de cards por conta descrito na seção 1.

### Mapeamento para a API real

Contas em si:

```ts
interface ContaCriar {
  nome: string;
  cor?: string;
  ordem?: number;
  tipo?: "corrente" | "cartao_credito";       // default "corrente"
  dia_vencimento_fatura?: number | null;       // obrigatório quando tipo=cartao_credito
  conta_pagamento_padrao_id?: number | null;
}
interface ContaOut {
  id: number;
  nome: string;
  cor: string;
  ordem: number;
  ativa: boolean;
  tipo: "corrente" | "cartao_credito";
  dia_vencimento_fatura: number | null;
  conta_pagamento_padrao_id: number | null;
}
```

`GET`/`POST /contas`, `PATCH /contas/{id}`, `DELETE /contas/{id}`
(desativa se em uso). **Nenhum desses campos inclui saldo** — a ausência
do mock (`saldo`, `faturaEmAberto` direto no objeto `Conta`) foi uma
simplificação deliberada e correta para o mock, mas não existe assim na
API real: saldo e fatura em aberto vêm de `GET /anos/{ano}/resumo`
(`por_conta`/`por_cartao`, ver seção 1), casados pelo `conta_id`. A tela
real precisa de duas fontes de dado — `useContas()` para a lista/CRUD,
`useResumo(ano)` para os números — não uma.

Fatura do cartão (o botão "Pagar fatura"):

```ts
interface FaturaOut {
  cartao_id: number; ano: number; mes: number;
  valor_em_aberto: string;              // Decimal como string
  situacao: "pendente" | "pago";
  lancamento_id: number | null;
  dia_vencimento: number;
}
```

- `GET /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}` — situação real (o
  mock aproxima isso com `faturasPagas` local; a integração troca por esta
  chamada, uma por cartão). **`{mes}` é parte do caminho, não query
  string** — corrigido depois de uma verificação real contra a API feita
  pela conversa do backend (branch `spec-etapa-a-e-validacao-extra`); a
  versão anterior deste documento tinha `?mes={mes}` por engano, herdado de
  uma inconsistência que já existia em `CONTRATO-API.md` desde antes desta
  rodada.
- `POST /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/pagar` — corpo
  opcional `{ conta_pagamento_id?: number }`; idempotente (chamar de novo
  com a fatura já paga devolve o mesmo lançamento, sem duplicar — a
  segunda chamada também responde `201`, não `200`, o status vem fixo do
  decorador da rota; não muda nada para quem consome). É o que o botão
  "Confirmar pagamento" do Dialog `pagando` deve chamar, no lugar do
  `setFaturasPagas` mock.
- `POST /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/desfazer` — `204`,
  sem corpo.

Nenhuma decisão de produto pendente aqui — é wiring direto.

---

## 9. Gastos Fixos (`/gastos-fixos`)

### O que a tela mostra hoje (mock, pós-Etapa A)

Rota nova, lista de gastos fixos com checkbox "Pago" por linha (referente
ao mês selecionado no filtro do cabeçalho — ou ao mês corrente, quando o
filtro está em "Ano inteiro"), Dialog de criar/editar, exclusão.

### Mapeamento para a API real

```ts
interface GastoFixoCriar {
  descricao: string;
  valor: string;
  dia_vencimento?: number;               // default 1
  forma_pagamento?: "credito" | "debito" | "pix" | "dinheiro" | null;
  categoria_id?: number | null;
  conta_id: number;
}
interface GastoFixoMensalOut { mes: number; situacao: "pendente" | "pago"; lancamento_id: number | null; }
interface GastoFixoOut {
  id: number; ano_id: number; descricao: string; valor: string;
  dia_vencimento: number;
  forma_pagamento: "credito" | "debito" | "pix" | "dinheiro" | null;
  categoria_id: number | null; conta_id: number; ativo: boolean;
  meses: GastoFixoMensalOut[];
}
```

- `GET /anos/{ano}/gastos-fixos`, `POST` (cria), `PATCH /{id}`, `DELETE
  /{id}` (remove o modelo; lançamentos já gerados por ele permanecem).
- **O checkbox "Pago" não é um PATCH de campo — são dois endpoints
  próprios**, que criam/removem o lançamento de verdade:
  `POST /anos/{ano}/gastos-fixos/{gasto_id}/meses/{mes}/pagar` (`201`,
  devolve o `LancamentoOut` criado; idempotente — chamar de novo com o mês
  já pago devolve o mesmo lançamento) e
  `POST /anos/{ano}/gastos-fixos/{gasto_id}/meses/{mes}/desfazer` (`204`,
  apaga o lançamento gerado). O `marcarSituacao(id, mes, situacao)` do
  `GastosFixosProvider` mock vira, na integração, essas duas chamadas — não
  uma atualização de campo local.
- `forma_pagamento_legado` (campo de texto livre do backend, ver
  `CONTRATO-API.md` do repo back) não tem equivalente no mock e não
  precisa ganhar um agora — é só histórico de importação antiga.

---

## 10. Wishlist (`/wishlist`)

### O que a tela mostra hoje (mock, pós-Etapa A)

Rota nova: lista de desejos com checkbox "somar", badge de importância,
marcar comprado, criar/editar/excluir, e um rodapé comparando o total
marcado (não comprado) com um `totalGuardadoMock` fixo.

### Mapeamento para a API real

```ts
interface DesejoCriar {
  desejo: string; valor?: string;
  importancia?: "alta" | "media" | "baixa";  // default "media"
  somar?: boolean;
}
interface DesejoOut {
  id: number; ano_id: number; desejo: string; valor: string;
  importancia: "alta" | "media" | "baixa"; somar: boolean; comprado: boolean;
}
interface TotalWishlist { total_marcado: string; total_geral: string; quantidade_marcada: number; }
```

- `GET /anos/{ano}/wishlist`, `POST`, `PATCH /{id}` (inclui marcar
  `comprado`), `DELETE /{id}`.
- `GET /anos/{ano}/wishlist/total` — substitui o cálculo local
  `items.filter(...).reduce(...)` que a tela faz hoje; já vem pronto do
  backend, não precisa ser recalculado no cliente.
- **O "total guardado" do rodapé (`totalGuardadoMock`) não tem endpoint
  próprio** — é a soma de `guardado` por conta corrente, que já existe em
  `ResumoAnoOut.por_conta[].guardado` (o mesmo `GET /anos/{ano}/resumo` do
  Dashboard). A integração troca a constante mock por essa soma, sem
  precisar de nenhum endpoint novo.

---

## 11. Calendário de Vencimentos (componente embutido no Dashboard)

Não é uma tela própria — é `CalendarioVencimentos.tsx`, renderizado dentro
do Dashboard. Já lê de `useGastosFixos()`/`useAccounts()`, então, na
integração, passa a ler dos mesmos hooks de React Query das seções 8 e 9
(`useGastosFixos(ano)`/`useContas()`) — nenhum endpoint novo, nenhuma
mudança de lógica de marcação de dia, só troca a origem dos dois arrays que
já consome.

---

## 12. Perfil real, Meta de Poupança e Alertas de Vencimento (ADR-06)

Contrato novo — nenhum destes endpoints existe ainda no backend no momento
em que esta seção foi escrita. Ver `docs/adr/ADR-06-*.md` para o raciocínio
completo por trás de cada decisão de formato.

### Perfil — nome

```ts
// GET /auth/eu passa a incluir nome
interface UsuarioOut {
  id: number;
  email: string;
  nome: string | null;
}

// PATCH /auth/eu
interface UsuarioAtualizar {
  nome?: string;
}
```

### Meta de poupança

Duas formas simultâneas possíveis: uma meta mensal recorrente e uma meta
com prazo, cada uma com no máximo uma instância ativa por vez. Criar uma
meta nova do mesmo tipo desativa a anterior.

```ts
interface MetaPoupancaCriar {
  tipo: "mensal" | "prazo";
  valor_alvo: string;                 // Decimal como string, como o resto da API
  data_alvo?: string | null;          // ISO date; obrigatório quando tipo="prazo"
}

interface MetaAtivaMensal {
  id: number;
  valor_alvo: string;
  guardado_no_mes: string;            // soma de lançamentos "guardado" do mês corrente
  percentual: number;                 // 0-100+, guardado_no_mes / valor_alvo
}

interface MetaAtivaPrazo {
  id: number;
  valor_alvo: string;
  data_alvo: string;
  dias_restantes: number;
  guardado_acumulado: string;         // soma de "guardado" desde a criação da meta
  percentual: number;
}

// GET /metas-poupanca/ativas
interface MetasAtivasOut {
  mensal: MetaAtivaMensal | null;
  prazo: MetaAtivaPrazo | null;
}

// POST /metas-poupanca → cria e ativa (desativando a anterior do mesmo tipo)
// GET /metas-poupanca → histórico completo (ativas e desativadas), opcional para uma tela de histórico futura
// DELETE /metas-poupanca/{id} → desativa sem criar outra por cima
```

Esta é a implementação real do que a seção 7 chamava de `goals` na tela
`/metas` — a lista `budgets` (orçamento por categoria) da mesma tela
**continua mocada e fora de escopo**, sem relação com este contrato.

### Alertas de vencimento

Consulta computada, sem tabela própria — só itens não pagos com vencimento
dentro de 3 dias (constante do backend nesta primeira versão).

```ts
// A API gera oneOf + discriminator: tipo no OpenAPI (dois schemas Pydantic
// distintos, não um schema com campos opcionais) — o TypeScript estreita o
// tipo sozinho a partir de `tipo`, sem cast:
//   if (alerta.tipo === "fatura") { alerta.nome_cartao }  // já funciona
type AlertaOut =
  | { tipo: "gasto_fixo"; gasto_fixo_id: number; nome: string; dia_vencimento: number; valor: string; dias_restantes: number }
  | { tipo: "fatura"; cartao_id: number; nome_cartao: string; dia_vencimento_fatura: number; valor: string; dias_restantes: number };

// GET /alertas → AlertaOut[]
```

`dia_vencimento` (gasto fixo) e `dia_vencimento_fatura` (cartão)
propositalmente **não** foram uniformizados num nome só — em todo o resto
da API esses dois campos significam coisas diferentes, e manter os nomes
distintos aqui evita que o front leia o campo errado assumindo que
significam a mesma coisa. `valor` (o valor do gasto fixo ou da fatura em
aberto) é novo nos dois tipos, para o alerta mostrar quanto está vencendo,
não só o quê.

Cobre só vencimento de gasto fixo/fatura — não inclui progresso de meta de
poupança nem saldo baixo (fora de escopo nesta rodada, ver ADR-06).

### Preferência de alerta por e-mail

```ts
// PATCH /auth/eu (mesmo endpoint do nome, campo adicional)
interface UsuarioAtualizar {
  nome?: string;
  alertas_email_ativo?: boolean;
}
```

O envio de e-mail em si (o mecanismo que de fato manda a mensagem) é uma
fase de backend separada e posterior — o front só deve mostrar o toggle
depois que essa fase estiver pronta, para não repetir o problema que a
seção 6 já identificava (controle na tela que não faz nada de verdade). Até
lá, `alertas_email_ativo` pode existir na API sem nenhum efeito observável.

---

## 13. Importação de extrato (`/importacao`) — ADR-08

Tela **nova, do zero** — não existe rota nem componente de importação no
frontend hoje. O backend, ao contrário, já tinha o subsistema inteiro pronto e
testado (prévia, confirmação, deduplicação, sugestão de categoria); esta
rodada só o generalizou de OFX para os três formatos. Ler o `ADR-08` antes de
desenhar a tela.

### O fluxo tem dois passos, e o primeiro não grava nada

O extrato diz quanto entrou e saiu, mas não o que aquilo significa: um Pix
recebido pode ser salário ou devolução de um amigo; uma transferência para a
poupança parece saída, mas é `guardado`. Por isso a prévia é obrigatória —
o backend sugere, a pessoa decide, e só a confirmação escreve no banco.

### Passo 1 — prévia

```ts
// POST /anos/{ano}/importacao/previa
// multipart/form-data — os dois campos são obrigatórios:
//   arquivo: File
//   formato: "csv" | "xlsx" | "ofx"
//
// O formato NÃO é deduzido da extensão: a tela tem o seletor de qualquer
// forma, e adivinhar esconderia o engano mais provável (escolher "csv" e
// enviar o OFX), que hoje responde 422 com mensagem legível.

interface TransacaoPrevia {
  fitid: string;                        // identificador da transação; a chave do dedupe
  data: string;                         // "AAAA-MM-DD"
  valor: string;                        // decimal como string, sempre positivo
  descricao: string;
  tipo_sugerido: TipoLancamento;        // vem do sinal do valor: "saida" | "entrada"
  categoria_sugerida_id: number | null; // só para saídas, e só se houver regra
  categoria_sugerida_nome: string | null;
  duplicado: boolean;                   // já existe lançamento com este fitid
  possivel_repetido: boolean;           // mesma data e valor, fitid diferente
  fora_do_ano: boolean;                 // data fora do ano sendo editado
}

interface PreviaImportacao {
  total_lidas: number;
  ja_importadas: number;                // quantas vieram com duplicado = true
  transacoes: TransacaoPrevia[];
}
```

Erros possíveis: `422` com `detail` legível (arquivo vazio, formato errado,
planilha sem as colunas esperadas, data ou valor ilegível — a mensagem cita a
linha), `413` (acima de 10 MB) e `409` (o ano está arquivado).

### Passo 2 — confirmação

```ts
// POST /anos/{ano}/importacao/confirmar → 201
interface TransacaoConfirmar {
  fitid: string;                        // devolver o mesmo que veio da prévia
  data: string;
  valor: string;                        // positivo
  tipo: TipoLancamento;
  conta_id: number;                     // ver "a conta" abaixo
  conta_destino_id?: number | null;     // transferência
  destino?: DestinoRendimento | null;
  categoria_id?: number | null;
  forma_pagamento?: FormaPagamento | null;  // o extrato não informa; opcional
  descricao?: string;
  aprender_padrao?: string | null;      // cria a regra de categorização
}

interface ResultadoImportacao {
  importadas: number;
  ignoradas_duplicadas: number;         // revalidado no servidor, não confia na prévia
  regras_criadas: number;
}
```

**A conta** é pedida por transação, mas raramente muda dentro de um arquivo:
a tela pode ter um seletor único no topo da prévia e aplicá-lo a todas as
linhas ao montar o payload. Nenhuma mudança de backend é necessária para isso.

### O que a tela precisa fazer com os três sinalizadores

| Sinalizador | Comportamento esperado na tela |
| --- | --- |
| `duplicado` | Ocultar por padrão, com um "mostrar duplicadas" para conferir. Não adianta enviar: o backend ignora na confirmação de qualquer jeito. |
| `possivel_repetido` | Mostrar em destaque e **desmarcada por padrão** — opt-in, não opt-out, para não duplicar lançamento quando a pessoa passa o olho rápido. |
| `fora_do_ano` | Desmarcada e sinalizada. Se for enviada mesmo assim, a confirmação inteira responde `422`. |

### Layout aceito em CSV e XLSX

Três colunas identificadas **pelo nome do cabeçalho**, em qualquer ordem,
ignorando acentos e maiúsculas: `data`, `valor`, `descricao`. Valor **com
sinal** (negativo = saída), data em `AAAA-MM-DD` ou `DD/MM/AAAA`. O parser
tolera preâmbulo antes do cabeçalho, separador `;`/`,`/tabulação, BOM do
Excel, Latin-1, `R$` e separador de milhar.

É um formato **da aplicação**, não o export nativo de um banco — ainda não
conferido contra um arquivo real. Se divergir, o ajuste é isolado dentro de
`app/services/tabular.py` no backend e **não muda nada nesta seção**.

### Opcional nesta rodada, mas sem custo de backend

`aprender_padrao` já existe: ao corrigir a categoria de uma linha, oferecer um
"lembrar essa categoria da próxima vez" grava a regra junto com a confirmação
e a sugestão passa a vir pronta nas importações seguintes.

---

## Resumo — todos os endpoints usados por esta integração

| Método | Rota | Usado por |
| --- | --- | --- |
| `POST` | `/auth/login` | Login |
| `GET` | `/auth/eu` | Verificação de sessão na abertura do app |
| `GET` | `/anos/{ano}/resumo` | Dashboard, Tabela Dinâmica, Mês-detalhe, saldo/fatura por conta (seção 8), total guardado da Wishlist (seção 10) |
| `GET`/`POST`/`PATCH`/`DELETE` | `/anos/{ano}/lancamentos` | Lançamentos, Mês-detalhe |
| `GET`/`POST`/`PATCH`/`DELETE` | `/categorias` | Configurações → Categorias, e alimenta o `<select>` de categoria em Lançamentos e Gastos Fixos |
| `GET`/`POST`/`PATCH`/`DELETE` | `/contas` | Configurações → Contas, e alimenta o `<select>` de conta em Lançamentos e Gastos Fixos |
| `GET`/`POST`/`{mes}/pagar`/`{mes}/desfazer` | `/anos/{ano}/cartoes/{cartao_id}/fatura` | Botão "Pagar fatura" em Configurações → Contas |
| `GET`/`POST`/`PATCH`/`DELETE`/`{gasto_id}/meses/{mes}/pagar`/`.../desfazer` | `/anos/{ano}/gastos-fixos` | Gastos Fixos, Calendário de Vencimentos |
| `GET`/`POST`/`PATCH`/`DELETE`, `GET .../total` | `/anos/{ano}/wishlist` | Wishlist |
| `PATCH` | `/auth/eu` | Perfil → nome, preferência de alerta por e-mail (seção 12, ADR-06) |
| `GET`/`POST`/`DELETE` | `/metas-poupanca`, `GET /metas-poupanca/ativas` | Perfil e `/metas` → meta de poupança real (seção 12, ADR-06) |
| `GET` | `/alertas` | Painel de alertas de vencimento (seção 12, ADR-06) |
| `POST` | `/anos/{ano}/importacao/previa`, `.../confirmar` | Tela de importação de extrato (seção 13, ADR-08) |
| `GET`/`POST`/`DELETE` | `/regras` | Regras de categorização usadas pela importação (seção 13) |

Todos os endpoints das seções 1–11 já existiam e foram conferidos linha a
linha contra o código real do backend — nenhum precisou ser criado para
aquela rodada. Os quatro últimos da tabela acima (seção 12) são o único
domínio novo deste pacote, decidido pelo ADR-06: nome, meta de poupança e
alertas de vencimento. `budgets` (orçamento por categoria, dentro da tela
`/metas`) continua fora de escopo, sem endpoint — ver seção 7 e o
`ADR-0007` do repositório back.
