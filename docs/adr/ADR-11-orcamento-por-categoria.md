# ADR-11 — Orçamento por categoria: limite real e editável

**Status:** aceito

## Contexto

É o item 4 do `backlog-refinado.md`, já com as decisões de produto
resolvidas lá (limite sempre recorrente, ultrapassar 100% é só efeito
visual) — faltava só formalizar em ADR e mandar para implementação, o
que a Kamilly pediu agora explicitamente ao ver a tela "Metas &
Orçamentos" com os limites por categoria ainda mockados.

**Isto reverte o `ADR-0007` do repositório back.** Aquele ADR decidiu,
conscientemente, não rastrear "o que a pessoa pretendia gastar" — só "o
que de fato aconteceu" — e por isso a tela hoje mostra os limites
(Moradia R$ 2.600, Alimentação R$ 1.200, etc.) como dados de exemplo
fixos no frontend, com um aviso explícito disso na tela. O raciocínio do
ADR-0007 não estava errado — é uma decisão legítima sobre que informação
o sistema rastreia — só que a Kamilly, depois de usar o site, decidiu
que quer essa informação de verdade. Reverter uma decisão anterior por
causa de uso real é diferente de ter pulado a decisão sem pensar: por
isso isto vira um ADR novo, não uma edição silenciosa do ADR-0007.

O acompanhamento de **gasto real** por categoria (os R$ 17,00 de
Transporte, R$ 127,74 de Lazer no print que a Kamilly mandou) **já é
real hoje** — vem da mesma agregação de lançamentos que a Tabela
Dinâmica e o Dashboard já usam. A única peça que falta é o **limite**
em si ser um valor de verdade, editável, guardado no backend — hoje é
só uma constante no frontend.

## Decisão

### Limite mensal vira campo da própria `Categoria`

Em vez de criar uma entidade nova, o limite é só um campo a mais na
`Categoria` que já existe — mais simples, e reaproveita o CRUD de
categorias que a seção 5 já documenta:

```ts
interface CategoriaCriar {
  nome: string;
  cor?: string;
  limite_mensal?: string | null;   // Decimal como string, opcional
}
interface CategoriaAtualizar {
  nome?: string;
  cor?: string;
  ativa?: boolean;
  limite_mensal?: string | null;   // null explícito remove o limite
}
interface CategoriaOut {
  id: number;
  nome: string;
  cor: string;
  ativa: boolean;
  limite_mensal: string | null;
}
```

`limite_mensal` é sempre **recorrente** — o mesmo valor todo mês, sem
variar mês a mês nesta primeira versão (decisão já registrada no
backlog: mantém o v1 simples, no mesmo espírito de `GastoFixo`). Editar
o limite vale a partir da edição — o mês corrente recalcula a % na hora,
sem reescrever histórico.

Nem toda categoria precisa ter limite — `limite_mensal: null` é o
padrão, e continua sendo uma categoria de uso normal, só sem
acompanhamento de orçamento.

### Progresso — nenhuma conta nova, já existe

O "gasto atual" de cada categoria no mês já é uma agregação que existe
(`GET /anos/{ano}/resumo` já devolve `gastos_por_categoria` no
`ResumoMesOut` — ver seção 1). A tela de Metas & Orçamentos casa esse
valor com o `limite_mensal` da categoria (vindo de `GET /categorias`)
para montar a barra de progresso — cálculo do lado do frontend, sem
endpoint novo para isso.

Ultrapassar 100%: só o indicador muda (cor do texto/barra) — nenhum
alerta em outro canal é criado, consistente com o que o `ADR-06` já
decidiu para o escopo de alertas (só vencimento de gasto fixo/fatura).

### Toggle "mostrar orçamento" — preferência da pessoa, não da categoria

```ts
// PATCH /auth/eu (mesmo endpoint de nome/alertas_email_ativo do ADR-06)
interface UsuarioAtualizar {
  nome?: string;
  alertas_email_ativo?: boolean;
  mostrar_orcamento_categoria?: boolean;   // novo, default true
}
```

É uma preferência da conta, não de cada categoria — desligar não apaga
nenhum `limite_mensal` já cadastrado, só esconde a seção "Orçamentos por
categoria" da tela (reaproveitando o mesmo campo em `GET /auth/eu`).
Ficar salvo no backend em vez de `localStorage` porque a Kamilly já
instalou o app como PWA num aparelho e pode abrir do navegador em outro
— a preferência deve seguir a conta, não o dispositivo (mesmo raciocínio
já usado para `alertas_email_ativo`).

## Consequências

- Migração pequena: `Categoria.limite_mensal` (Decimal, nullable) e
  `Usuario.mostrar_orcamento_categoria` (boolean, default `true`).
- Nenhum endpoint novo — `PATCH /categorias/{id}` e `PATCH /auth/eu` já
  existem, só ganham um campo a mais cada.
- Nenhuma mudança na agregação de gasto por categoria — ela já existe e
  já está correta.
- O aviso "dados de exemplo — sem endpoint no backend (ADR 0007)" que a
  tela mostra hoje deixa de fazer sentido e sai, já que o limite passa a
  ser real.
- Isto substitui a "Decisão necessária" da seção 7 original da spec
  (que apontava para o `ADR-0007`) — ver a seção 16 nova, com o contrato
  completo.

## Alternativas consideradas

- **Entidade `OrcamentoCategoria` separada**, em vez de um campo na
  `Categoria`, para deixar mais explícito que é uma configuração
  opcional — descartada por adicionar uma tabela e um endpoint novos
  para guardar essencialmente um único campo opcional; um campo
  nullable na categoria já cumpre isso sem esse custo.
- **Limite configurável mês a mês**, não só recorrente — descartada
  nesta rodada pela mesma razão já registrada no backlog: mantém o v1
  simples; pode virar extensão futura se a necessidade aparecer no uso
  real.
- **Preferência "mostrar orçamento" no `localStorage`** em vez de no
  backend — descartada porque a Kamilly já usa o site em mais de um
  aparelho/navegador (instalou o PWA), e a preferência deveria seguir a
  conta, não ficar presa a um dispositivo específico.
