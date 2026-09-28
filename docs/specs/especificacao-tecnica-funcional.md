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

### Dashboard clicável → Lançamentos filtrado (ADR-07)

Os cards **"Entradas do Período"** e **"Saídas do Período"** viram links
para `/lancamentos?tipo=entrada` e `/lancamentos?tipo=saida`, com `cursor:
pointer` e feedback visual de hover. O mês não entra na URL — Dashboard e
Lançamentos já compartilham o mesmo mês/ano via `usePeriod()` (contexto
global), então o filtro de mês chega correto sem trabalho adicional. Ver
seção 2 para o lado de Lançamentos (como `tipo` é lido da URL).

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

### Filtro por tipo via URL (ADR-07)

A rota `/lancamentos` ganha `validateSearch` (TanStack Router) aceitando
`tipo?: TipoLancamento`. Ao montar a página, se `tipo` vier na URL,
inicializa o `useState` `tipoFiltro` já existente com esse valor — sem
criar um segundo lugar para esse estado morar. O backend já aceita `tipo`
(e `mes`) como query params em `GET /anos/{ano}/lancamentos` hoje —
nenhuma mudança de backend para este item.

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
  limite_mensal?: string | null;   // Decimal como string — ver seção 16, ADR-11
}
interface CategoriaAtualizar {
  nome?: string;
  cor?: string;
  ativa?: boolean;
  limite_mensal?: string | null;
}
interface CategoriaOut {
  id: number;
  nome: string;
  cor: string;
  ativa: boolean;
  limite_mensal: string | null;    // novo — ver seção 16, ADR-11
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
tela ganhou contrato de API real — ver seção 12.

**Atualização (ADR-11):** a parte de **orçamento por categoria**
(`budgets`), que o texto original abaixo (e o `ADR-0007` do repositório
back) tratava como fora de escopo, **deixou de ser mock** — ganhou
contrato real, ver seção 16. O texto da seção "Decisão necessária" logo
abaixo é histórico — descreve por que ficou de fora até aqui, não o
estado atual.

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

**Atualização (ADR-13):** esse "Total guardado" continua existindo do jeito
que está (reserva geral, sem mudança), mas deixa de ser o único número da
tela — ver seção 17 para o vínculo com metas de poupança (progresso por
item, e um segundo card no rodapé só com o que está guardado nas metas
vinculadas). Ver também seção 19 para os três ajustes de UI pedidos nesta
rodada (mensagem "Desejo adicionado" que não sumia, layout mobile da lista
em pé, nomes de mês por extenso).

---

## 11. Calendário de Vencimentos (componente embutido no Dashboard)

Não é uma tela própria — é `CalendarioVencimentos.tsx`, renderizado dentro
do Dashboard. Já lê de `useGastosFixos()`/`useAccounts()`, então, na
integração, passa a ler dos mesmos hooks de React Query das seções 8 e 9
(`useGastosFixos(ano)`/`useContas()`) — nenhum endpoint novo, nenhuma
mudança de lógica de marcação de dia, só troca a origem dos dois arrays que
já consome.

### Tooltip ao passar o mouse sobre um dia (ADR-07)

Hover num dia com algo agendado mostra um **tooltip flutuante** (não
altera o layout dos dias vizinhos) listando todos os itens agendados
daquele dia, não só o primeiro. Em mobile, sem hover: tap no dia
abre/fecha o tooltip. Puramente visual — nenhum dado novo, nenhum
endpoint novo.

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

> **Superado em parte pelo ADR-13 (seção 17):** a restrição "no máximo uma
> instância ativa por tipo" abaixo **não vale mais** — várias metas mensais
> e várias com prazo podem estar ativas ao mesmo tempo, cada uma podendo
> opcionalmente se vincular a um item da wishlist. O formato de
> `MetaPoupancaCriar` e o de `GET /metas-poupanca/ativas` mudam — ver seção
> 17 para o contrato atualizado. O texto original abaixo fica só como
> registro histórico do que o ADR-06 decidiu primeiro.

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
também deixou de ser mock, mas por um contrato separado: ver seção 16
(ADR-11).

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

## 13. Importação de extrato bancário — CSV, XLSX e OFX (ADR-08)

Ver `docs/adr/ADR-08-*.md` para o raciocínio completo. Diferente das
seções anteriores, isto **não é um contrato 100% novo**: o backend já tem
um subsistema de importação completo para OFX (prévia + confirmação,
deduplicação, sugestão de categoria) — o que muda aqui é generalizar para
CSV/XLSX e construir a tela no frontend, que hoje não existe.

**Status do backend (31/08/2026):** a generalização já está implementada,
testada e **em produção** — as duas rotas abaixo respondem para os três
formatos, e o caminho antigo (`/importacao/ofx/previa`, `.../ofx/confirmar`)
responde `404`. O que falta deste item é só a tela.

### Fluxo

Dois passos, de propósito — nada é gravado na prévia:

```ts
// POST /anos/{ano}/importacao/previa
// multipart: arquivo (File) + formato: "csv" | "xlsx" | "ofx" | "pdf"
// Os dois campos são obrigatórios. O formato NÃO é deduzido da extensão:
// a tela tem o seletor de qualquer forma, e adivinhar esconderia o engano
// mais provável — escolher "csv" e enviar o OFX, que hoje dá 422 legível.

interface TransacaoPrevia {
  fitid: string;                       // identificador de dedupe — ver nota abaixo
  data: string;                        // "YYYY-MM-DD"
  valor: string;                       // Decimal como string, sempre positivo
  descricao: string;
  // No OpenAPI o campo é TipoLancamento (os 7 valores), mas a prévia só
  // produz estes dois — o sentido vem do sinal do valor no extrato:
  tipo_sugerido: "entrada" | "saida";
  categoria_sugerida_id: number | null;
  categoria_sugerida_nome: string | null;
  duplicado: boolean;        // já existe lançamento com este fitid — ignorado na confirmação, sem perguntar
  possivel_repetido: boolean; // mesma data+valor de um lançamento existente, fitid diferente — vai para a tela de conferência
  fora_do_ano: boolean;       // data fora do ano sendo editado
}

interface PreviaImportacao {
  total_lidas: number;
  ja_importadas: number;      // quantas já são `duplicado`
  transacoes: TransacaoPrevia[];
}
```

```ts
// POST /anos/{ano}/importacao/confirmar

interface TransacaoConfirmar {
  fitid: string;
  data: string;
  valor: string;              // > 0
  tipo: TipoLancamento;
  conta_id: number;           // escolhida na tela, não no upload — ver decisão abaixo
  conta_destino_id?: number | null;
  destino?: "conta" | "guardado" | null;
  categoria_id?: number | null;
  forma_pagamento?: "credito" | "debito" | "pix" | "dinheiro" | null;
  descricao?: string;
  aprender_padrao?: string | null;  // opcional: grava regra de categorização ao confirmar
}

interface ConfirmarImportacao {
  transacoes: TransacaoConfirmar[];
}

interface ResultadoImportacao {
  importadas: number;
  ignoradas_duplicadas: number;   // revalidado no servidor, mesmo que o front já tenha filtrado
  regras_criadas: number;
}
```

### Erros

Ambas as rotas devolvem `{ detail: string }` legível (ADR-01) — a mensagem
pode ir direto para a tela:

| Código | Quando |
| --- | --- |
| `422` | Arquivo vazio; formato errado para o arquivo enviado; planilha sem as colunas esperadas; data ou valor ilegível (**a mensagem cita a linha**); na confirmação, transação com data fora do ano |
| `413` | Arquivo acima de 10 MB |
| `409` | O ano está arquivado |

Na confirmação, uma única linha `fora_do_ano` faz a chamada **inteira**
falhar com `422` — nada é gravado. A tela precisa filtrar essas linhas antes
de enviar, não confiar em o backend ignorá-las.

### Deduplicação — `fitid`

Para OFX, `fitid` vem do próprio arquivo (`FITID`) quando existe; quando
não existe, e **sempre** para CSV/XLSX (que não têm identificador de
transação nativo), o backend sintetiza um identificador estável a partir
de `data + valor com sinal + descrição (até 40 caracteres)` — já
implementado e testado para o caso OFX-sem-FITID, reaproveitado sem mudança
para os formatos novos. Único por `(ano, fitid)`, o que faz `duplicado` e a
idempotência de reimportar o mesmo extrato funcionarem de graça.

**O sinal faz parte da chave** (a versão anterior desta seção dizia só "data
+ valor"): sem ele, um Pix enviado e um recebido no mesmo dia, de mesmo
valor e mesma descrição, colidiriam e o segundo sumiria como duplicata.

**Quarta coluna, opcional: `identificador`.** O extrato em CSV do Nubank —
conferido de verdade em 31/08 — traz um UUID por transação, que é o mesmo
papel do `FITID`. Quando a coluna existe, o `fitid` é esse valor em vez do
sintético, e a deduplicação fica exata. Nada muda para a tela.

### PDF — só de bancos conhecidos (ADR-12)

PDF não tem layout padrão: cada banco organiza a página do seu jeito, e o
arquivo guarda como desenhar, não o que cada pedaço significa. Por isso o
backend tem **um leitor por banco**, e hoje conhece dois: **Nubank** e
**Mercado Pago** (extrato de conta). Qualquer outro PDF é recusado com `422` e
mensagem explicando.

Isso é deliberado: um leitor genérico erraria calado no extrato do Mercado
Pago, onde cada linha traz dois valores (o da transação e o saldo corrente) e
pegar o errado importaria números plausíveis e falsos.

Para a tela, três coisas:

1. **Não prometer PDF em geral.** Sugestão de texto no seletor: "PDF funciona
   para Nubank e Mercado Pago. Para outros bancos, use OFX, CSV ou XLSX."
2. **Destacar o `total_lidas` da prévia quando o formato for `pdf`.** Num PDF a
   maior parte do texto nunca foi transação, então linha não reconhecida é
   ignorada em silêncio — esse número é como a pessoa percebe que o extrato
   tinha 40 lançamentos e vieram 12.
3. **Fatura de cartão não é lida**, só extrato de conta. Faturas escrevem a
   data sem ano (`26/07`), e inferir o ano jogaria lançamento para o ano
   errado.

Erros com mensagem própria, prontos para exibir: PDF escaneado (imagem, sem
texto), layout de banco desconhecido, e PDF protegido por senha de verdade.

**PDF e CSV do mesmo extrato não deduplicam entre si**, porque o PDF do Mercado
Pago usa o `ID da operação` do banco e o CSV usa outro identificador. Quem
importar os dois vê as linhas marcadas como `possivel_repetido`, já
desmarcadas — o aviso funciona, mas vale não sugerir na interface que importar
os dois é seguro.

### Layout aceito para CSV/XLSX

Três colunas, identificadas pelo nome do cabeçalho (case-insensitive,
ordem livre): `data` (`AAAA-MM-DD` ou `DD/MM/AAAA`), `valor` (negativo =
saída, positivo = entrada, mesma convenção do OFX), `descricao`. É um
layout genérico da própria aplicação, não o export nativo de nenhum
banco — se o extrato real tiver colunas diferentes, é um ajuste isolado só
no parser, sem afetar o resto do contrato.

O parser tolera o que um arquivo real costuma trazer: preâmbulo antes do
cabeçalho, separador `;`/`,`/tabulação, BOM do Excel, Latin-1, `R$` e
separador de milhar. Linhas em branco e de valor zero são ignoradas. O que
ele **não** faz é engolir erro em silêncio: data ou valor ilegível
interrompe a importação citando a linha.

### Tela de importação (frontend — não existe hoje)

1. Seletor de formato (CSV/XLSX/OFX) + upload do arquivo + seletor de
   conta (aplicado a todas as linhas do lote na confirmação).
2. Tela de conferência: uma linha por transação. `duplicado` fica oculta
   por padrão (com opção de mostrar). `possivel_repetido` aparece
   destacada e **desmarcada por padrão** — opt-in para importar, não
   opt-out, para não duplicar por engano.
3. Confirmar envia só o que ficou marcado, com o `conta_id` escolhido no
   passo 1.

### Regras de categorização (já existem, usadas pela sugestão automática)

```ts
// GET /regras, POST /regras (cria ou atualiza pelo padrão), DELETE /regras/{id}
interface RegraOut {
  id: number;
  padrao: string;
  categoria_id: number;
  categoria: CategoriaOut;
}
```

---

## 14. PWA instalável — manifest.json e ícones (ADR-09)

Ver `docs/adr/ADR-09-*.md` para o raciocínio completo. Não é contrato de
API — é só frontend: um `manifest.json` novo e um conjunto de ícones,
para que "Adicionar à tela de início" no celular gere um ícone e um nome
de verdade, com o app abrindo em tela cheia (`display: standalone`), em
vez do comportamento genérico de hoje.

```json
{
  "name": "Planejamento Financeiro",
  "short_name": "Financeiro",
  "description": "Controle entradas, saídas, orçamentos e metas em um painel moderno.",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#6c2cba",
  "orientation": "portrait-primary",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

Ícones (`public/icons/`), gerados a partir do `newicon.svg` que já é a
identidade visual atual do projeto: `icon-192.png`, `icon-512.png`,
`icon-maskable-512.png` (com mais espaço de respiro, para o recorte
"maskable" do Android) e `apple-touch-icon.png` (180×180, fundo opaco).

Tags novas no `<head>` (além das que já existem hoje — nenhuma muda):

```html
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#6c2cba">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Financeiro">
```

Sem service worker nesta rodada (decisão do ADR-09) — o app não funciona
offline; isso continua sendo o item 7 do backlog, tratado à parte.

---

## 15. Investimentos — caixinhas por conta (ADR-10)

Ver `docs/adr/ADR-10-*.md` para o raciocínio completo. Tela nova
("Investimentos"), entidade nova (`Caixinha`), e extensões pequenas em
`Lancamento` e em `GET /metas-poupanca/ativas` (sem quebrar o contrato
que já existe).

**Status do backend (03/09/2026):** implementado e **em produção**. O contrato
abaixo vale como está; os detalhes que o ADR não tinha como antecipar aparecem
marcados ao longo da seção.

```ts
interface CaixinhaOut {
  id: number;
  conta_id: number;
  nome: string;
  meta_id: number | null;
  // Calculado pelo backend, não é campo editável: `saldo_inicial` mais o
  // efeito dos lançamentos que apontam para a caixinha. Vem pronto.
  saldo: string;          // Decimal como string
  criada_em: string;      // datetime
  ativa: boolean;
}

interface CaixinhaCriar {
  nome: string;
  meta_id?: number | null;
  saldo_inicial?: string; // Decimal, default "0.00" — validado contra o
                          // guardado ainda sem caixinha na conta
}
// 422 quando `saldo_inicial` passa do guardado sem caixinha. A mensagem traz
// os dois números ("Esta conta tem R$ 200,00 guardado ainda sem caixinha, e
// você pediu R$ 500,00") — dá para mostrar direto na tela.
//
// 422 também ao criar caixinha num cartão de crédito: cartão não tem reserva
// (ADR-0002). A tela deve oferecer só contas `tipo="corrente"` no seletor.
//
// `meta_id` precisa apontar para uma meta ATIVA; meta desativada dá 422.

interface CaixinhaAtualizar {
  nome?: string;
  meta_id?: number | null;   // enviar null explicitamente para desvincular
  saldo_inicial?: string;    // Decimal; `null` é recusado — para zerar, "0"
}
// `saldo_inicial` é editável depois da criação (mudou em 05/09/2026 — a
// primeira versão só aceitava na criação, e quem esquecia de preencher
// perdia o único momento de rotular o dinheiro que já estava guardado).
//
// Mesmo teto da criação, mais o que esta caixinha já reivindicava: 422 com o
// valor máximo na mensagem. Baixar demais também dá 422, se deixaria a
// caixinha negativa.

// GET/POST/PATCH/DELETE /contas/{conta_id}/caixinhas
```

Transferência direta entre duas caixinhas da mesma conta:

```ts
interface TransferenciaCaixinha {
  caixinha_origem_id: number;
  caixinha_destino_id: number;
  valor: string; // Decimal, > 0, ≤ saldo da caixinha de origem
}

// POST /contas/{conta_id}/caixinhas/transferir
// → 201, devolvendo a CaixinhaOut de DESTINO já com o saldo novo
// → cria um Lancamento com tipo="transferencia_caixinha" (não conta
//   como entrada/saída do período, não muda o total de guardado da conta)
//
// A data é hoje — o corpo não tem campo de data. Por isso o ano corrente
// precisa existir: se não existir, 422 pedindo para criá-lo; se estiver
// arquivado, 409.
//
// 422 quando o valor passa do saldo da origem (a mensagem traz o saldo) e
// quando origem ou destino está desativada. 404 quando alguma das duas não
// é daquela conta.
```

`LancamentoCriar`/`LancamentoOut` ganham `caixinha_id` (opcional — a
caixinha de destino em `guardado`, de origem em `retirado`, ou em
`rendimento`/`perda` com `destino="guardado"`) e `caixinha_destino_id`
(só usado em `tipo="transferencia_caixinha"`, junto com `caixinha_id`
como origem). Os dois são opcionais e não quebram nenhum lançamento ou
integração que já existe hoje sem eles.

`GET /metas-poupanca/ativas` não muda de schema — só passa a calcular
`guardado_no_mes`/`guardado_acumulado` a partir das caixinhas vinculadas
(`caixinha.meta_id`), quando houver alguma, em vez do total da
conta/ano. Sem caixinha vinculada, continua exatamente como o `ADR-06`
já define.

Só as caixinhas **ativas** contam: desativar uma devolve o dinheiro dela ao
guardado sem rótulo, e a meta volta ao cálculo do ADR-06.

### Conta com caixinhas exige escolher uma

Assim que a conta tem **pelo menos uma caixinha ativa**, todo lançamento que
mexe na reserva dela precisa mandar `caixinha_id`: `guardado`, `retirado`, e
`rendimento`/`perda` com `destino="guardado"`. Sem ele, `422` — e a mensagem
lista os nomes das caixinhas disponíveis, para a tela mostrar as opções.

`entrada`, `saida` e transferência entre contas não são afetadas.

Para a tela: o seletor "Caixinha", quando a conta escolhida tiver caixinhas,
**não é opcional** naqueles tipos — vira campo obrigatório. Numa conta sem
caixinha nenhuma o seletor não aparece e nada muda.

A mesma regra vale na confirmação da importação, que por isso aceita
`caixinha_id` em cada `TransacaoConfirmar`.

### Caixinha nunca fica negativa

Qualquer operação que deixaria uma caixinha abaixo de zero responde `422`,
dizendo qual caixinha e quanto faltaria. Vale para criar lançamento, editar,
excluir e transferir.

Duas consequências para a tela:

- **Excluir um lançamento pode falhar.** Apagar o `guardado` que financiou
  uma retirada posterior é recusado — a tela precisa tratar `422` no `DELETE`
  de lançamento, não só nos `POST`/`PATCH`.
- **Editar valor ou tipo pode falhar pelo mesmo motivo**, mesmo sem tocar em
  `caixinha_id`.

Esvaziar até exatamente zero é permitido — a regra é sobre ficar negativa.

### Guardado sem caixinha — a tela calcula, não tem endpoint

A diferença entre o guardado da conta e a soma das caixinhas dela não tem rota
própria: é `por_conta[].guardado` de `GET /anos/{ano}/resumo` menos a soma dos
`saldo` de `GET /contas/{id}/caixinhas`, casando pelo `conta_id`. Mesmo padrão
da seção 8, onde o saldo da conta também vem do resumo e não de `GET /contas`.

Numa conta já organizada esse número tende a **zero** — todo guardado tem
caixinha. Ele só é maior que zero enquanto houver dinheiro lançado antes de as
caixinhas existirem, e é esse saldo que `saldo_inicial` consome.

### Desativar uma caixinha

`DELETE` é soft-delete, como em metas e categorias: a caixinha some da lista
(`incluir_inativas=true` a traz de volta) e o saldo dela volta a ser guardado
sem rótulo da conta. Nenhum lançamento é apagado, e `GET /anos/{ano}/resumo`
não muda — o dinheiro nunca saiu da conta.

---

## 16. Orçamento por categoria — limite real e editável (ADR-11)

Ver `docs/adr/ADR-11-*.md`. Reverte o `ADR-0007` do back — o limite por
categoria deixa de ser dado de exemplo do frontend e vira campo real da
própria `Categoria` (sem entidade nova, sem endpoint novo — só dois
campos a mais em endpoints que já existem).

**Status do backend (05/09/2026):** implementado e testado. Duas regras que o
ADR não especificava aparecem marcadas abaixo.

```ts
// Categoria ganha limite_mensal (ver seção 5 para a interface completa)
// GET /categorias já devolve limite_mensal em cada item
// PATCH /categorias/{id} já aceita limite_mensal (null remove o limite)
//
// Campo AUSENTE e campo NULO querem dizer coisas diferentes: mandar só
// { cor } preserva o limite; mandar { limite_mensal: null } o remove.
//
// O limite precisa ser MAIOR QUE ZERO — 0 ou negativo respondem 422. "Sem
// orçamento" se escreve com null, não com zero; um teto de zero não diz nada.
// Desativar a categoria não mexe no limite.

// PATCH /auth/eu ganha um campo novo, junto dos que o ADR-06 já definiu:
interface UsuarioAtualizar {
  nome?: string;
  alertas_email_ativo?: boolean;
  mostrar_orcamento_categoria?: boolean;   // novo, default true
}
```

O "gasto atual" de cada categoria no mês **já existe** —
`ResumoMesOut.gastos_por_categoria` (seção 1) é a mesma agregação que
alimenta a Tabela Dinâmica. A tela de Metas & Orçamentos casa esse valor
com `limite_mensal` (de `GET /categorias`) para montar a barra de
progresso — cálculo no frontend, sem chamada nova.

Limite é sempre recorrente (mesmo valor todo mês, sem variar por mês
nesta versão). Ultrapassar 100% é só efeito visual (cor muda) — nenhum
alerta em outro canal, mesmo escopo de alertas que o `ADR-06` já fechou.

O aviso "dados de exemplo — sem endpoint no backend (ADR 0007)" que a
tela mostra hoje sai — o limite passa a ser real.

`GET /auth/eu` passa a devolver `mostrar_orcamento_categoria` junto dos campos
que já devolvia. Ele nasce `true`, inclusive para a conta que já existia —
vem do default da coluna, sem migração de dados. Desligar **não apaga** limite
nenhum: é preferência de exibição, não de dado.

Uma categoria sem limite (`null`) continua aparecendo normalmente em
`gastos_por_categoria` — ela só não tem barra de progresso.

---

## 17. Metas de poupança viram lista, com vínculo opcional à wishlist (ADR-13)

Ver `docs/adr/ADR-13-*.md` para o raciocínio completo. Reverte parte do
ADR-06: deixa de existir o limite de "uma meta ativa por tipo".

```ts
interface MetaPoupancaCriar {
  tipo: "mensal" | "prazo";
  nome?: string;                      // novo, opcional — rótulo livre
  valor_alvo: string;
  data_alvo?: string | null;          // obrigatório quando tipo="prazo"
  wishlist_item_id?: number | null;   // novo, opcional — id de um ItemWishlist
}

interface ProgressoMetaMensalOut {
  id: number;
  nome: string | null;
  wishlist_item_id: number | null;
  valor_alvo: string;
  guardado_no_mes: string;
  percentual: number;
}
interface ProgressoMetaPrazoOut {
  id: number;
  nome: string | null;
  wishlist_item_id: number | null;
  valor_alvo: string;
  data_alvo: string;
  guardado_acumulado: string;
  percentual: number;
  dias_restantes: number;
}
// GET /metas-poupanca/ativas — mesma rota, corpo muda de par nulável pra listas:
interface MetasAtivasOut {
  mensais: ProgressoMetaMensalOut[];   // era `mensal: ProgressoMetaMensalOut | null`
  prazos: ProgressoMetaPrazoOut[];     // era `prazo: ProgressoMetaPrazoOut | null`
}
```

- `POST /metas-poupanca` não aposenta mais a meta anterior do mesmo tipo —
  cria uma nova, independente. `wishlist_item_id`, se enviado, precisa
  apontar pra um item que existe (`422` se não existir).
- `DELETE /metas-poupanca/{id}` continua igual — desativa por id, nunca
  apaga de verdade.
- **Tela `/metas` e `MetaPoupancaSection.tsx`** (mesmo componente, usado
  também em Configurações → Perfil): passam de dois blocos fixos
  (mensal/prazo) pra duas listas. O formulário de nova meta ganha "Nome
  (opcional)" e um `<select>` "Vincular a um item da wishlist (opcional)",
  populado com os itens não comprados do ano corrente (`GET
  /anos/{ano}/wishlist`, mesmo hook que a tela de Wishlist usa).
- **Tela `/wishlist`:** passa a buscar também `GET /metas-poupanca/ativas`.
  Pra cada item, filtra `[...mensais, ...prazos].filter(m =>
  m.wishlist_item_id === item.id)` (sem endpoint novo, sem N+1) e mostra o
  progresso de cada meta vinculada na própria linha do item — meta `prazo`
  mostra `guardado_acumulado / valor_alvo`; meta `mensal` mostra
  `guardado_no_mes / valor_alvo` com o rótulo "guardado este mês" (são
  medidas diferentes, não somar as duas). O card "Total guardado" do
  rodapé (seção 10) continua como está; um card novo, "Guardado nas metas
  vinculadas", soma só `guardado_acumulado` das metas tipo `prazo`
  vinculadas a itens não comprados do ano corrente.

---

## 18. Parcelamento no cartão de crédito, com juros opcional (ADR-14)

Ver `docs/adr/ADR-14-*.md` para o raciocínio completo, inclusive a tabela
dos três modos de cálculo (sem juros / com juros por valor da parcela / com
juros por taxa %) e a justificativa de usar juros simples em vez da Tabela
Price.

```ts
interface CompraParceladaCriar {
  descricao: string;
  conta_id: number;
  categoria_id?: number;
  data_primeira_parcela: string;         // YYYY-MM-DD
  numero_parcelas: number;               // 2..24
  tem_juros: boolean;
  modo_juros?: "valor" | "percentual";   // obrigatório se tem_juros=true
  valor_total?: string;                  // obrigatório se !tem_juros ou modo_juros="percentual"
  valor_parcela?: string;                // obrigatório se modo_juros="valor"
  taxa_juros_pct?: string;               // obrigatório se modo_juros="percentual"
}
interface CompraParceladaOut {
  id: number;
  descricao: string;
  numero_parcelas: number;
  tem_juros: boolean;
  modo_juros: "valor" | "percentual" | null;
  taxa_juros_pct: string | null;
  valor_parcela: string;
  valor_total: string;
  parcelas: LancamentoOut[];             // as N linhas já geradas, uma por mês
}
```

- `POST /anos/{ano}/compras-parceladas` — gera as N linhas de `Lancamento`
  de uma vez (não sob demanda). Cria silenciosamente os anos que faltarem
  pras parcelas futuras (zero saldos iniciais); `422` se algum ano de
  destino já existir arquivado.
- `DELETE /anos/{ano}/compras-parceladas/{id}` — apaga o grupo; em cascata,
  remove as parcelas que ainda existirem como lançamento, em qualquer ano.
- Uma parcela isolada continua sendo editável/excluível pelo
  `PATCH`/`DELETE /anos/{ano}/lancamentos/{id}` que já existe — nenhuma
  regra nova ali; editar uma parcela não recalcula as outras.
- **Formulário de novo lançamento:** com `forma_pagamento=crédito`, ganha
  um alternador "Parcelar" (desligado por padrão). Ligado: número de
  parcelas (campo numérico com botões `−`/`+` **visíveis na tela**, não as
  setinhas nativas do `<input type="number">` — o Safari/iOS as esconde
  completamente, e o uso é majoritariamente mobile), alternador "Tem
  juros?", e os campos condicionais da tabela do ADR-14 conforme o modo
  escolhido.
- **Tela de Lançamentos:** mostra "3/10" nos lançamentos que têm
  `numero_parcela`/`compra_parcelada_id` preenchidos, com ação "Excluir
  compra inteira" ao lado da exclusão individual já existente.

---

## 19. Ajustes de UI pedidos nesta rodada — sem endpoint novo

Três ajustes puramente de frontend, sem nenhuma mudança de contrato com o
backend.

### Layout da Wishlist no mobile em pé

A linha de cada item (`wishlist.tsx`) hoje é um único `flex` horizontal sem
nenhum breakpoint — checkbox, nome truncado, badge de importância, valor de
largura fixa (`w-28`) e três ícones de ação, todos na mesma linha. Num
celular em pé (~360–400px de largura) isso não cabe: o nome trunca cedo
demais e os ícones de ação ficam espremidos ou cortados.

Abaixo do breakpoint `sm` (Tailwind, ~640px), a linha vira duas linhas
dentro do mesmo item: nome + badge de importância na primeira, valor +
ações na segunda (ou um layout de cartão empilhado, ao critério de quem
implementar — o requisito é: nome do desejo nunca trunca de um jeito que
esconda a informação principal, e os três botões de ação (marcar
comprado/editar/excluir) continuam com alvo de toque de pelo menos 40×40px
cada). Acima de `sm`, mantém a linha única atual.

### Toast "Desejo adicionado" com tempo pra sumir e X pra fechar

O `Toaster` global (`components/ui/sonner.tsx`, montado em
`routes/__root.tsx`) não define `duration` nem `closeButton` hoje — herda o
padrão da biblioteca (Sonner), que é 4000ms e sem botão de fechar visível.
Se na prática o toast está ficando na tela indefinidamente, o motivo não
está nesse componente (vale confirmar em runtime antes de mexer, pode ser
uma interação específica de mobile/PWA). De qualquer forma, o pedido é
tornar o comportamento **explícito** em vez de depender do padrão
implícito da biblioteca:

```tsx
<Sonner
  duration={4000}
  closeButton
  toastOptions={{ ... /* classNames já existentes, sem mudança */ }}
  {...props}
/>
```

`closeButton` adiciona um X clicável em todo toast do app (não só
"Desejo adicionado" — é uma prop global do `Toaster`, não dá pra ligar só
numa mensagem específica sem duplicar o componente). Isso já cobre "poder
fechar antes se preferir".

### Nomes dos meses por extenso

`MONTHS` (`lib/finance-data.ts`) hoje é `["Jan", "Fev", ..., "Dez"]` e
alimenta: o `<select>` de mês no `AppShell` (troca livre, `<option>` não
tem limite de largura), os títulos/subtítulos de várias telas (troca
livre), os cabeçalhos da Tabela Dinâmica (já dentro de uma tabela
`overflow-x-auto` com `min-w-[1000px]` — já rola horizontalmente, nome
completo só aumenta um pouco a largura que já rola) e o eixo X do gráfico
de barras do Dashboard (`routes/index.tsx`, `<XAxis dataKey="mes"
fontSize={12}>`, sem rotação nem espaçamento pra 12 rótulos longos).

Decisão (confirmada com a Kamilly): `MONTHS` vira nomes completos em todo
lugar —

```ts
export const MONTHS = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];
```

— **exceto** o eixo do gráfico do Dashboard, que ganha um array próprio só
pra esse uso:

```ts
export const MONTHS_ABREVIADOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
```

`routes/index.tsx` troca `MONTHS[m.mes - 1]` por `MONTHS_ABREVIADOS[m.mes - 1]`
só na construção do array `monthly` que alimenta o `<XAxis dataKey="mes">`
— o `subtitle` da mesma tela (`${MONTHS[month - 1]} de ${year}`) continua
usando `MONTHS` (nome completo), sem mudança.

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
| `GET`/`POST`/`DELETE` | `/metas-poupanca`, `GET /metas-poupanca/ativas` | Perfil e `/metas` → meta de poupança real (seção 12, ADR-06; corpo de `/ativas` e payload de criação mudam na seção 17, ADR-13) |
| `GET` | `/alertas` | Painel de alertas de vencimento (seção 12, ADR-06) |
| `POST` | `/anos/{ano}/importacao/previa`, `/anos/{ano}/importacao/confirmar` | Tela de importação de extrato — CSV/XLSX/OFX (seção 13, ADR-08). Já implementado para os três formatos e em produção; o caminho antigo `/ofx/...` responde `404` |
| `GET`/`POST`/`DELETE` | `/regras` | Sugestão automática de categoria na importação (seção 13) — já existe, não tinha entrado nesta tabela antes por não ser consumido por nenhuma tela até agora |
| `GET`/`POST`/`PATCH`/`DELETE` | `/contas/{conta_id}/caixinhas`, `POST .../transferir` | Tela nova de Investimentos (seção 15, ADR-10) |
| `POST`/`DELETE` | `/anos/{ano}/compras-parceladas` | Parcelamento no crédito, novo endpoint (seção 18, ADR-14) — ainda não implementado |

Todos os endpoints das seções 1–11 já existiam e foram conferidos linha a
linha contra o código real do backend — nenhum precisou ser criado para
aquela rodada. Os da seção 12 são o domínio novo decidido pelo ADR-06:
nome, meta de poupança e alertas de vencimento. Os da seção 13
(importação) já existem para OFX — o ADR-08 generaliza para CSV/XLSX; a
tela em si é nova no frontend. `budgets` (orçamento por categoria, dentro
da tela `/metas`) deixou de ficar fora de escopo — o ADR-11 reverte o
`ADR-0007` do repositório back; ver seção 16 (sem endpoint novo, só
campos a mais em `/categorias` e `/auth/eu`, que já existiam). A seção 17
(ADR-13) muda o formato de dois endpoints que já existem, sem criar
nenhum novo. A seção 18 (ADR-14) é o único domínio desta rodada com
endpoint genuinamente novo (`/anos/{ano}/compras-parceladas`). A seção 19
(ajustes de UI) não toca em nenhum endpoint.
