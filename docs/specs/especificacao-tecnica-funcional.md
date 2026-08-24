# Especificação Técnica e Funcional — Integração do frontend Lovable com o backend FastAPI

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
- **Faltam os cartões de crédito na tela.** `por_cartao` existe e não tem
  hoje nenhum widget equivalente no Lovable — é a fatura em aberto de cada
  cartão. Não é bloqueante para esta rodada (a tela funciona sem isso), mas
  é uma perda de informação real se ficar de fora — recomenda-se um KPI ou
  card adicional "Fatura em aberto" na Parte 3, mesmo que simples.
- **"Lançamentos recentes"** pode continuar vindo de
  `GET /anos/{ano}/lancamentos?mes={mes}` (ver seção 2) ordenado por data,
  já que o resumo não traz a lista crua.

---

## 2. Lançamentos (`/lancamentos`)

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

### O que a tela mostra hoje (mock)

Pivô categoria × mês, com um seletor "Saídas / Entradas", somando
`transactions` no cliente.

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

### O que a tela mostra hoje (mock)

Uma lista somente-leitura de chips com os nomes fixos de `CATEGORIES` — não
tem criar, editar nem apagar.

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

## Resumo — todos os endpoints usados por esta integração

| Método | Rota | Usado por |
| --- | --- | --- |
| `POST` | `/auth/login` | Login |
| `GET` | `/auth/eu` | Verificação de sessão na abertura do app |
| `GET` | `/anos/{ano}/resumo` | Dashboard, Tabela Dinâmica, Mês-detalhe |
| `GET`/`POST`/`PATCH`/`DELETE` | `/anos/{ano}/lancamentos` | Lançamentos, Mês-detalhe |
| `GET`/`POST`/`PATCH`/`DELETE` | `/categorias` | Configurações → Categorias, e alimenta o `<select>` de categoria em Lançamentos |
| `GET` | `/contas` | Alimenta o `<select>` de conta em Lançamentos (obrigatório, ver seção 2) |

Nenhum endpoint novo é necessário no backend para esta rodada — o gap está
inteiramente do lado do frontend (campos que faltam nos formulários) e de
duas telas (`Metas & Orçamentos`, parte de `Configurações`) que dependem de
domínio que o backend deliberadamente ainda não tem.
