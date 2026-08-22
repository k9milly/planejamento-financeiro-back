# ADR-0005 — Motor de arrastar/redimensionar: biblioteca pronta, não construído do zero

**Status:** substituído pelo [ADR-0008](0008-canvas-infinito.md)

> O pedido original ("blocos ajustáveis") foi esclarecido numa rodada
> seguinte para "canvas infinito, estilo planilha, sem limite de área" —
> algo que `react-grid-layout` (a escolha deste ADR) não faz, por ser uma
> grade responsiva de largura fixa que só cresce para baixo. O raciocínio
> abaixo continua registrado porque explica por que uma biblioteca pronta
> foi preferida a construir do zero — esse princípio segue válido, só a
> biblioteca escolhida mudou. Ver ADR-0008 para a decisão atual.

## Contexto

O pedido é que os blocos do modo painel sejam "totalmente
customizáveis": maiores, menores, movidos de lugar. Isso é um problema de
interface conhecido — arrastar com o mouse/toque, redimensionar por uma
alça no canto, decidir o que acontece quando um bloco solto esbarra em
outro (colisão/reflow), e continuar funcionando numa tela menor.

O frontend hoje não tem nenhuma dependência além de React e Tailwind (ver
`package.json`) — é um projeto que evita dependência por princípio (ver
`docs/ARQUITETURA.md`, "Por que não há biblioteca de estado no frontend").
Vale então explicar por que esta é uma exceção justificada, e não uma
contradição com essa política.

## Decisão

Usar uma biblioteca pronta de grade arrastável/redimensionável —
`react-grid-layout` — só dentro do `ModoPainel`. O `ModoPlanilha` não
ganha essa dependência; continua exatamente como está.

`react-grid-layout` recebe uma lista de itens com posição e tamanho em
unidades de grade (`{ i: id, x, y, w, h }`) e devolve um `<div>` que já
sabe arrastar, redimensionar (alça no canto), evitar sobreposição
(reflow automático empurra o que está no caminho) e recalcular em telas
menores (breakpoints responsivos). O app só precisa fornecer o layout
inicial e escutar o evento `onLayoutChange` para persistir (ADR-0006).

## Por que uma dependência aqui, quando o projeto evita dependência em outros lugares

A política existente evita dependência **quando o problema já está
resolvido por `useState`/`useEffect`** — foi assim que o projeto decidiu
não usar Redux/React Query (o fluxo de dados é simples demais para
justificar). Arrastar-e-redimensionar-com-colisão-e-responsividade **não**
é esse tipo de problema: é física de interação (drag, touch, teclado para
acessibilidade, cálculo de colisão, redistribuição dos vizinhos) que leva
muito código para acertar direito, e que várias bibliotecas já resolveram
e testaram em produção há anos. Reescrever isso do zero é o tipo de
esforço que não sobra valor nenhum para o usuário final — ele nunca vai
notar se o motor de arrasto foi escrito à mão ou importado, só vai notar
se ele tem bugs.

Em outras palavras: a política do projeto não é "nunca dependências", é
"nenhuma dependência para resolver algo que já é simples aqui". Isto não é
simples aqui.

## Por que `react-grid-layout`, e não outra

- É a biblioteca mais madura e usada nesse nicho especificamente para
  React (dashboards no estilo Grafana/Notion usam ela ou algo no mesmo
  molde); tem suporte a breakpoints responsivos de fábrica, que o app
  precisa para não quebrar em telas menores.
- Guarda o estado de layout como um JSON simples (`x, y, w, h` por item) —
  exatamente o formato que precisa ser persistido (ADR-0006), sem tradução.
- Tem um modo "estático" próprio (`isDraggable`/`isResizable` por item ou
  global) que serve de base pronta para o "modo de edição vs. modo de
  visualização" descrito na spec — evita implementar esse controle à mão.

## Consequências

- Nova dependência de build: `react-grid-layout` (+ seu CSS, que precisa
  ser importado uma vez). É a primeira dependência de UI do frontend além
  de React/Tailwind — vale registrar isso no `README.md` do frontend
  quando implementado.
- Só o `ModoPainel` a importa; um `import` isolado nesse módulo evita que
  o bundle do `ModoPlanilha` cresça por causa de uma dependência que ele
  não usa (o Vite já faz isso por tree-shaking de módulo, mas vale garantir
  na revisão de código que nada de `ModoPainel` vaza para fora).
- Cada tipo de widget (spec seguinte) precisa ter um tamanho mínimo
  (`minW`/`minH`) sensato — um gráfico de rosca espremido a menos de
  100px não serve pra nada. Isso é configuração por widget, não um
  problema da biblioteca.

## Alternativas consideradas

- **`dnd-kit`.** Mais flexível e menor, mas resolve só o "arrastar" — a
  lógica de grade, colisão e redimensionamento teria que ser escrita por
  cima, à mão. Rejeitada: paga o custo de uma dependência nova sem herdar
  o problema já resolvido.
- **`gridstack.js`.** Resolve o mesmo problema, mas não é uma biblioteca
  React nativa (é vanilla JS com um wrapper por cima) — mais atrito para
  integrar com o resto do app, que é 100% React. Rejeitada em favor de uma
  opção que já pensa em componentes.
- **Construir do zero com CSS Grid + eventos de mouse manuais.** Rejeitada
  pelo motivo explicado acima — é reinventar um problema já resolvido, com
  risco real de bugs sutis (arrasto que "pula", redimensionamento que não
  respeita o mínimo, nada funcionando em touch) que uma biblioteca madura
  já não tem.
