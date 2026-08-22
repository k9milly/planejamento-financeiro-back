# ADR-0004 — Dois modos de visualização, alternados por um botão, com "planilha" como padrão

**Status:** proposto

## Contexto

O pedido é manter a interface atual (12 páginas, uma por mês, no molde de
planilha) como uma opção, e criar uma segunda interface — um painel único,
no estilo mostrado na imagem de referência anexada: cartões de resumo,
gráficos, calendário e tabelas, tudo numa tela só, com visual escuro e
gráficos que a interface atual não tem.

O usuário nomeou os dois modos: **modo planilha** — o que já existe, com
layout fixo, sem nada arrastável — e **modo painel** — o novo, da imagem,
que é justamente o oposto: todo customizável (ver ADR-0008). Uso esses
dois nomes ao longo de todos os documentos desta rodada.

(Nota de correção: as duas primeiras versões deste documento usavam "modo
estático" para o modo novo — leitura errada da minha parte na primeira
menção ao pedido. O usuário esclareceu depois: "estático" descrevia o modo
**planilha** — de layout fixo, não customizável —, não o painel, que é
exatamente o modo pensado para ser mexível. Todos os documentos desta e
da rodada anterior foram corrigidos para "modo painel".)

## Decisão

Um hook `useModoVisual`, no mesmo molde de `useTema` (`lib/tema.ts`):
preferência lida do `localStorage` (chave `planejamento:modo-visual`),
padrão `planilha` quando não há escolha salva. Um botão no cabeçalho, ao
lado do `BotaoTema`, alterna entre os dois.

`App.tsx` passa a decidir **o quê** renderizar depois de carregar os dados
(resumo, lançamentos, contas, gastos fixos, desejos) — os dois modos
consomem os **mesmos** dados já buscados, nenhum dos dois refaz a
requisição por conta própria. Na prática, a árvore de componentes que hoje
é o corpo de `App.tsx` passa a ser extraída para um componente
`ModoPlanilha`, e um novo `ModoPainel` é adicionado ao lado — `App.tsx`
escolhe um dos dois com base no hook.

## Por que o padrão é "planilha", e não perguntar na primeira visita

Ninguém que já usa o app hoje deve ver a tela mudar sozinha na primeira
vez que abrir depois do deploy. "Planilha" como padrão silencioso (igual
ao tema, que segue o sistema só na ausência de escolha) preserva o
comportamento atual para todo mundo até a pessoa decidir experimentar o
novo modo.

## Por que os dois modos compartilham os dados carregados por `App.tsx`, e não buscam os seus próprios

Os dois modos mostram, em formatos diferentes, a mesma informação
(saldo, lançamentos, gastos fixos, contas). Buscar duas vezes duplicaria
chamadas de API sem necessidade e criaria uma janela em que os dois modos
poderiam mostrar números diferentes por terem recarregado em momentos
diferentes. Isso empurra para um pequeno refactor: hoje `App.tsx` já
concentra toda a busca de dados (`recarregar`, `carregarAnos`) — ela
continua concentrada ali, só passa a alimentar dois componentes filhos em
vez de um.

## Consequências

- `App.tsx` cresce um pouco de responsabilidade (escolher o modo), mas
  perde a lógica de exibição em si, que migra para `ModoPlanilha.tsx`
  (cópia do que já existe hoje, sem mudança de comportamento) e
  `ModoPainel.tsx` (novo).
- O botão de alternância só aparece depois que os dados do mês já
  carregaram — não faz sentido oferecer trocar de modo numa tela de
  carregamento.
- Trocar de modo não perde o mês/ano selecionado: `mesAtual`/`anoAtual`
  continuam vivendo em `App.tsx`, acima dos dois modos.
- Alguns containers do modo planilha (`GerenciadorContas`, `GastosFixos`,
  `CalendarioVencimentos`, etc.) são reaproveitados como fonte dos widgets
  do modo painel — não reescritos do zero. O detalhe de quais viram
  widget "as is" e quais ganham uma casca visual nova está na spec.

## Alternativas consideradas

- **Rota separada (`/painel`) com um roteador client-side.** Rejeitada
  pelo mesmo motivo que o projeto já não usa uma biblioteca de estado (ver
  `docs/ARQUITETURA.md`, "Por que não há biblioteca de estado no
  frontend"): o app não tem hoje nenhuma necessidade de rotas — introduzir
  `react-router` só para alternar dois modos numa página só seria uma
  dependência nova resolvendo um problema que um `useState` já resolve.
- **Preferência de modo salva no backend, como o layout customizado (ADR-0006).**
  Rejeitada para este campo especificamente: é uma preferência leve, de
  reconstituição trivial (um clique), no mesmo espírito do tema — não do
  layout arrastado, que representa esforço manual do usuário. Ver
  ADR-0006 para o contraste.
