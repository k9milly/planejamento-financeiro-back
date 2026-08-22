# ADR-0009 — Rolagem nativa com zoom em degraus, no molde do Google Sheets: refina o ADR-0008

**Status:** implementado

## Contexto

O ADR-0008 escolheu um canvas movido por `transform` — arrastar o fundo (ou
a roda do mouse) deslocava a posição, sem barra de rolagem nativa do
navegador, porque `scrollLeft`/`scrollTop` não vão a negativo e o pedido
original ("sem limite de área") sugeria que uma superfície verdadeiramente
sem borda era o objetivo.

Testado de verdade, isso saiu ruim: sem barra de rolagem, não há **nenhuma**
pista visual de "onde eu estou" dentro do canvas nem de "quanto ainda tem
para os lados" — o único jeito de saber é arrastar e ver o que aparece. E
não havia zoom nenhum: o tamanho dos widgets era fixo, sem como ver mais
coisa de uma vez numa tela grande, nem ampliar um bloco específico numa
pequena. A usuária pediu as duas coisas de volta, citando o Google Sheets
como referência — que tem as duas: barra de rolagem visível (nos dois
eixos) e um controle de zoom.

## Decisão

### Rolagem nativa do navegador, dentro de uma área grande porém finita

Troca o `<div>` movido por `transform: translate()` por um `<div>` comum
com `overflow: auto`, contendo um conteúdo de tamanho fixo (200 colunas ×
400 linhas = 48.000×48.000px no zoom 100%). Isso dá a barra de rolagem de
graça — é a barra nativa do navegador, nos dois eixos, com o comportamento
que a usuária já conhece de qualquer planilha ou documento.

A ressalva do ADR-0008 sobre `scrollLeft` não ir a negativo continua válida
e é resolvida do mesmo jeito que uma planilha de verdade resolve: um
deslocamento de origem. `ORIGEM_COL`/`ORIGEM_LIN` (40 células cada) reserva
espaço *antes* de `coluna=0`/`linha=0`; um widget em `coluna=-5` é
desenhado em `(40-5)×CELL_W` de pixel — sempre positivo, sem que
`scrollLeft` precise ser negativo. O widget entende que está em `-5`; o
DOM entende que está em `35`.

**A "sem limite de área" do pedido original vira uma área grande, não mais
uma pretensão de infinita.** É uma correção honesta, não só uma
simplificação de código: 48.000×48.000px é enorme para qualquer uso real
(a usuária precisaria arrastar um widget umas 200 células de distância do
que já existe para sentir a borda), mas é finito de verdade, exibido como
tal — ao contrário do canvas "infinito" do ADR-0008, que também tinha um
teto técnico (±24 milhões de px) só que escondido. Mostrar a barra de
rolagem é, inclusive, mostrar honestamente que existe um limite — o mesmo
espírito do Google Sheets, que também tem um teto (10 milhões de células) e
mostra a barra de rolagem sem esconder isso de ninguém.

### Zoom em degraus, ancorado no centro da tela

Um controle no canto inferior direito (mesmo lugar do Google Sheets):
`− 100% +`, com um clique no percentual voltando a 100%. Os degraus são
fixos — `25% 50% 75% 100% 125% 150% 175% 200%` — em vez de contínuos, para
o "encaixe" de célula continuar previsível em qualquer nível.

Tecnicamente, o zoom é um `transform: scale()` no mesmo `<div>` de
conteúdo que a rolagem nativa já usa — os navegadores modernos calculam
`scrollWidth`/`scrollHeight` a partir da caixa **depois** da transformação,
então a barra de rolagem já reflete o zoom automaticamente, sem nenhuma
conta manual de tamanho por célula. Um widget não precisa saber que existe
zoom: sua posição/tamanho continuam em unidades de célula (`CELL_W`/
`CELL_H` fixos), e é o `scale()` do ancestral que aumenta ou diminui tudo
junto — texto, gráfico, espaçamento.

Trocar de degrau mantém o ponto do canvas que está no centro da tela —
sem isso, cada clique no zoom "chutaria" a visão para outro lugar, a mesma
desorientação que a barra de rolagem deveria resolver, não recriar. Isso
exige uma ordem específica ao aplicar: o `transform: scale()` novo precisa
já estar no elemento *antes* de calcular o `scrollLeft`/`scrollTop` do
zoom novo — se o navegador ainda enxerga a área rolável do zoom antigo (menor)
na hora de aceitar o scroll, ele arredonda para o limite antigo. Por isso o
zoom mexe no `style` do elemento diretamente (via ref), na mesma função que
calcula e aplica o scroll, em vez de esperar o React re-renderizar primeiro.

### O que fica de fora

Arrastar o fundo para "pan" (como o ADR-0008 tinha) sai — rolagem nativa
(barra, roda do mouse, toque) já cobre o mesmo caso de uso, e é o que o
Google Sheets também faz (arrastar uma célula vazia começa uma seleção, não
um pan). Zoom contínuo (pinça no trackpad, `Ctrl`+roda) fica fora desta
correção — os degraus fixos resolvem o pedido, e zoom contínuo é uma
extensão de baixo custo se for pedido depois, já que a arquitetura
(`transform: scale()`) já comporta.

## Consequências

- O botão "Centralizar" (ADR-0008) muda de "reenquadra os widgets" via
  `transform` para um `scrollTo` — mesma ideia, mecanismo diferente.
- A virtualização (ADR-0008) passa a se basear em `scrollLeft`/`scrollTop`
  (lidos via um handler de `onScroll`) em vez da posição de pan.
- O arrasto (`dnd-kit`) e o redimensionar (alça própria) precisam dividir o
  delta do ponteiro pelo zoom atual antes de converter para células — o
  delta chega em pixels de tela, e o widget mora dentro de um wrapper já
  escalado.
- `docs/CONTRATO-API.md` não muda — o layout continua uma string opaca do
  ponto de vista do backend; só o significado de `coluna`/`linha` (agora
  relativas a uma origem deslocada, mas isso já era assim desde o
  ADR-0008) e a existência de uma área máxima (antes escondida, agora
  refletida numa barra de rolagem) mudam, e os dois são só do frontend.

## Alternativas consideradas

- **Manter o pan por `transform`, só acrescentando uma barra de rolagem
  "falsa"** (um indicador visual desenhado à mão, sem ser a barra nativa,
  arrastável). Rejeitada: reimplementa o que o navegador já faz de graça,
  com pior acessibilidade (teclado, leitor de tela) e mais código para
  manter em sincronia com o `transform`.
- **Continuar "infinito" e só acrescentar zoom.** Não resolve o pedido
  específico da usuária (barra de rolagem visível) — o problema relatado
  era justamente a falta de referência de posição, que zoom sozinho não
  resolve.
