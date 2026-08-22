# ADR-0005 — `react-grid-layout` como motor da grade, com um único layout mestre

**Status:** implementado

## Contexto

O modo painel (ADR-0004) precisa de blocos que a usuária arraste,
redimensione e que se reorganizem sozinhos quando um vizinho sai do lugar —
sem sobreposição, e refluindo em tela estreita.

Isso é bem mais do que parece: exige detecção de colisão, compactação
vertical, cálculo de posição em unidades de grade, alças de
redimensionamento e reflow por ponto de quebra.

## Decisão

Usar **`react-grid-layout`** (v2), que resolve tudo isso, em vez de escrever
o motor à mão. É a biblioteca padrão do ecossistema para este problema,
tem tipos próprios na v2 e não arrasta dependências de UI junto.

A grade tem **12 colunas** na tela larga, 6 na média e 2 na estreita.

### Um layout mestre só, o da tela larga

O ponto sutil: `ResponsiveGridLayout` aceita um layout por ponto de quebra,
e chama `onLayoutChange` sempre que reorganiza — **inclusive quando o reflow
foi causado só por a tela ter encolhido**.

Se o app persistisse esse layout refluído, bastaria abrir o painel uma vez
no celular para o arranjo de 12 colunas montado no PC ser sobrescrito pela
versão comprimida em 2 colunas — e perdido para sempre, inclusive no
servidor.

Por isso: **só o layout `lg` é guardado**. Os menores o
`react-grid-layout` deriva dele a cada render, e `onLayoutChange` ignora
qualquer mudança que aconteça fora da tela larga. Pela mesma razão, o modo
de edição só aparece na tela larga: numa pilha de uma coluna não há para
onde arrastar nada, e o resultado não seria salvo.

### Medição de largura própria

O hook `useContainerWidth` que a v2 oferece ficou preso na largura inicial
de fábrica (1280) neste layout, montando blocos de 400px dentro de uma tela
de 375. A largura é medida por um `ResizeObserver` próprio
(`ModoEstatico.tsx::useLarguraContainer`), com o evento `resize` da janela
como segundo gatilho — o observer sozinho não dispara em todo ambiente.

A medição é feita num `div` sem padding, e não no `<main>`: `clientWidth`
inclui o padding, e passar essa largura à grade faria os blocos vazarem.

## Consequências

- Duas folhas de estilo da biblioteca são importadas em `ModoEstatico.tsx`
  (`react-grid-layout/css/styles.css` e `react-resizable/css/styles.css`).
  Como o módulo é carregado sob demanda, esse CSS também é.
- Arrastar exige o punho (`.puxador`), que só existe no modo de edição.
  Fora dele a grade fica travada — os widgets têm botões e formulários
  dentro, e um arraste acidental sobre eles atrapalharia mais do que ajuda.
- O layout é guardado em unidades de grade (`x`, `y`, `w`, `h`), não em
  pixels: continua correto em qualquer largura de tela.

## Alternativas consideradas

- **Escrever o motor à mão** (CSS grid + arrastar próprio). Rejeitada: a
  parte difícil não é arrastar, é o que acontece com os *outros* blocos
  depois — colisão e compactação são onde este tipo de código erra, e não
  havia nada de específico do projeto que justificasse reescrevê-los.
- **Guardar um layout por ponto de quebra.** Rejeitada por agora: dobraria
  o que a usuária precisa manter arrumado, para resolver um problema que
  ela não tem — no celular ela usa a planilha, e a pilha de uma coluna que
  o reflow gera é a leitura certa ali.
