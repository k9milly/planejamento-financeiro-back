# ADR-0008 — Canvas infinito no modo painel: substitui a grade do ADR-0005

**Status:** implementado — **refinado pelo [ADR-0009](0009-scroll-nativo-e-zoom.md)**

> **Nota de atualização.** Testado de verdade, o pan por `transform` sem
> barra de rolagem deixou a usuária sem nenhuma referência de "onde eu
> estou" no canvas, e sem zoom não dava para ver mais ou menos coisa de
> uma vez. O ADR-0009 troca o mecanismo de rolagem (nativa do navegador,
> não mais `transform: translate()`) e acrescenta zoom em degraus — a
> decisão de ter um canvas maior que a tela, com coordenadas de célula que
> podem ser negativas e sem reflow ao soltar sobre outro widget, continua
> valendo; só a forma de rolar por ele mudou. O resto deste documento
> (extensão, virtualização, colisão bloqueada, `dnd-kit`) permanece a
> descrição correta do que está implementado.

## Nota de terminologia

Esta rodada esclareceu um mal-entendido meu: eu vinha chamando o modo
novo de "modo estático" desde a primeira menção a ele. O usuário
corrigiu: no app, **modo planilha** é o de layout fixo — por isso
"estático" —, e **modo painel** é o nome do modo novo, que é
justamente o customizável (o oposto de estático). Troquei "modo
estático" → "modo painel" em todos os documentos já entregues (ADRs
0004–0008, a spec, `CONTRATO-API.md`, os dois planos de implementação) —
não é mais uma questão de preferência de nome, é a correção do nome
errado que eu tinha usado.

## Contexto

O ADR-0005 escolheu `react-grid-layout` para o motor de arrastar/redimensionar
do modo painel. Essa biblioteca resolve um problema específico: uma grade
**responsiva de largura fixa** (N colunas que cabem na largura da tela) que
cresce só **para baixo**, conforme mais linhas são necessárias — é o modelo
do Grafana, do Notion, da maioria dos "dashboards customizáveis".

O pedido, esclarecido nesta rodada, é outro: uma tela **estilo
Excel/Google Sheets**, com **canvas infinito** — sem container de tamanho
fixo, sem borda delimitando uma área máxima, podendo rolar e adicionar
conteúdo **em qualquer direção** indefinidamente, como uma grade que cresce
sob demanda.

Isso não é um ajuste de configuração do `react-grid-layout` — é um modelo
de interação diferente na raiz: largura fixa responsiva vs. superfície
livre nas quatro direções. Por isso este é um ADR novo que **substitui**
o 0005, não um adendo a ele (o 0005 continua no repositório, com o status
atualizado, para registrar por que a decisão mudou — não é apagado).

### Sobre "sem `overflow: hidden`"

Vale uma precisão técnica, porque tomada ao pé da letra a frase é
irrealizável: qualquer tela tem uma janela de visualização finita (o
monitor do usuário), então em algum nível do DOM sempre existe um
elemento que recorta o que está fora da área visível — é assim que
`overflow: auto` (com barra de rolagem) funciona também, e é como o
próprio navegador exibe qualquer página. O que o pedido rejeita não é a
técnica de recorte da janela visível — é um **container com tamanho e
posição fixos que limita até onde o conteúdo pode existir**, tipo uma
`<div style="width: 1200px; height: 800px; overflow: hidden">` que corta
um widget colocado fora dela e não deixa rolar até lá. A diferença é entre
"a tela mostra um pedaço por vez" (inevitável, e ok) e "só existe aquele
pedaço" (o que está sendo rejeitado). O resto deste documento resolve o
segundo problema.

## Decisão

### Superfície de pan por transformação CSS, não scroll nativo do navegador

O canvas é uma `<div>` de conteúdo, posicionada por
`transform: translate(x, y)`, dentro de uma janela de visualização de
tamanho normal (a área da tela disponível). Arrastar no fundo do canvas
(fora de qualquer widget), ou usar a roda do mouse/trackpad, move essa
transformação — não existe uma barra de rolagem nativa do navegador
controlando a posição.

**Por que não usar o scroll nativo** (uma `<div>` gigante com
`overflow: auto`, como uma primeira ideia sugeriria): o scroll nativo do
navegador não tem posição negativa — `scrollLeft`/`scrollTop` começam em
zero e não vão para trás. Para permitir crescer para **cima** e para a
**esquerda** também (não só para baixo/direita, como uma planilha
convencional), seria necessário, toda vez que o conteúdo crescesse "para
trás", deslocar todo o conteúdo existente para a frente e ajustar a
posição de rolagem no mesmo instante, para a tela não "pular". Isso é uma
fonte clássica de bugs visuais (o conteúdo treme, ou pula, por um frame,
sempre que a extensão precisa crescer). Uma transformação controlada pelo
próprio app não tem essa restrição — mover para coordenadas negativas é
tão simples quanto mover para positivas.

### Grade de células com coordenadas podendo ser negativas

Cada widget ocupa um retângulo de células de tamanho uniforme (padrão
sugerido: 240×120px por célula, configurável), endereçado por
`(coluna, linha, largura_em_células, altura_em_células)` — igual ao
schema anterior (`ItemLayout`), exceto que `coluna`/`linha` agora são
inteiros **com sinal** (podem ser negativos), em vez de um índice de 0 a
11 preso à largura da tela. O primeiro widget que existe nasce perto da
origem `(0, 0)`; nada impede o usuário de arrastar um widget novo para
`(-3, -2)`, por exemplo.

### Extensão sob demanda

O app acompanha o retângulo `(colMin, colMax, linMin, linMax)`
efetivamente em uso (union de todos os widgets **e** de até onde o
usuário já rolou). Quando o pan chega a uma distância pequena de uma
dessas bordas, a área "disponível para rolar" cresce mais um tanto — na
prática, o usuário nunca vê nem sente um limite, porque a extensão sempre
está um passo à frente de onde ele consegue chegar rolando.

**Limite técnico honesto:** o app não expõe nenhum limite ao usuário, mas
internamente a extensão satura num valor muito grande (ex.: ±100.000
células, o equivalente a ±24.000.000 pixels) — necessário porque
navegadores têm um teto real de pixels que um elemento pode ocupar (por
volta de 33 milhões de pixels em alguns motores). É o mesmo tipo de
limite que o próprio Google Sheets tem (10 milhões de células) sem que
ninguém o perceba como "não é infinito de verdade" — na prática, ninguém
chega lá.

### Virtualização

Só os widgets cujo retângulo intersecta a janela de visualização atual
(mais uma margem, para o widget não "piscar" ao entrar na tela) são
efetivamente montados no DOM/React. Widgets fora da vista são
desmontados. Sem isso, um canvas com muitos widgets acumulados ao longo do
tempo (mesmo que a maioria fora de vista) ficaria progressivamente mais
pesado — cada widget tem conteúdo de verdade (gráfico, tabela), não é uma
caixa vazia.

### `dnd-kit` para arrastar, em vez de `react-grid-layout`

Sem a necessidade de um algoritmo de reflow (grade responsiva que empurra
vizinhos — ver próxima decisão), o problema volta a ser só "arrastar um
elemento e saber onde ele foi solto", que é exatamente o que `dnd-kit`
resolve bem (era a alternativa rejeitada no ADR-0005 por não cobrir grade
e colisão — aqui não precisamos que ele cubra isso, então a rejeição não
se aplica mais). Redimensionar é uma alça própria, pequena, arrastada
como um segundo tipo de gesto — não depende de nenhuma biblioteca de
grade.

### Sem reflow automático — sobreposição é bloqueada, não reorganizada

O `react-grid-layout` empurra automaticamente os vizinhos quando um widget
é solto sobre eles. Isso faz sentido numa grade responsiva compacta, onde
o espaço é escasso; num canvas infinito, espaço nunca falta — não há
motivo para reorganizar o que o usuário não tocou. A regra nova: soltar um
widget sobre células já ocupadas por outro widget é rejeitado (o widget
volta para a última posição válida, com um retorno visual rápido — ex.:
uma pequena animação de "elástico"). O usuário sempre pode arrastar para
uma célula livre ao lado, que num canvas infinito nunca está longe.

### Botão "Voltar à origem" / "Ajustar à tela"

Risco real de um canvas verdadeiramente infinito: o usuário se perde (rola
demais numa direção e não sabe mais voltar para onde os widgets estão). Um
botão fixo no canto ("Centralizar", ou ícone de mira) reposiciona o pan
para enquadrar todos os widgets existentes — sem isso, "infinito" vira
"perdido" na primeira sessão de uso descuidada.

### Zoom fica fora do escopo desta correção

O pedido não menciona zoom, só pan. A arquitetura por `transform` já
comportaria adicionar escala (`scale()`) depois, se for pedido — é uma
extensão barata desta decisão, não uma mudança de arquitetura, mas não
está sendo construída agora.

## Consequências

- **O backend não muda.** O contrato já tratava `layout` como uma string
  JSON opaca (`docs/CONTRATO-API.md`) — o formato interno do
  `ItemLayout` mudar (coordenadas com sinal em vez de 0–11) não exige
  nenhum ajuste em `docs/PLANO-BACKEND-pagamentos-e-painel.md`. Esta correção é 100% frontend.
- `docs/PLANO-FRONTEND.md`, Fases 7 e 8 (motor de grade e persistência),
  precisam ser reescritas para descrever `dnd-kit` + canvas por
  transformação em vez de `react-grid-layout` — ver as fases atualizadas.
  Se a implementação ainda não começou essas fases, é só trocar o plano;
  se já começou, o código de integração com `react-grid-layout` é
  descartado (nenhum widget individual precisa mudar — eles só recebem
  posição/tamanho de fora, não sabem como foram calculados).
- O breakpoint responsivo (`lg`/`md`/`sm`, herdado do Tailwind no ADR-0005)
  deixa de fazer sentido do jeito que estava — um canvas infinito não
  "reflui" para caber numa tela menor, ele continua do mesmo tamanho e o
  usuário rola mais para ver menos por vez. Em tela estreita, o pan por
  toque (um dedo arrasta o fundo) substitui a decisão anterior de
  "empilhar em ordem fixa sem arrasto" — arrastar o fundo para rolar é,
  na prática, mais simples de suportar em toque do que redimensionar por
  alça já era (o gesto de redimensionar por alça continua fora de escopo
  em toque, só o pan entra).
- O cursor "onde eu estou" se perde mais fácil que numa grade compacta —
  daí o botão de recentralizar ser parte da decisão, não um extra
  opcional.

## Alternativas consideradas

- **Manter `react-grid-layout` e tentar configurá-lo para não limitar
  largura.** A biblioteca recalcula a grade a partir da largura do
  container por design — forçá-la a se comportar como uma superfície
  infinita nas quatro direções é lutar contra a premissa central dela, não
  uma configuração. Rejeitada.
- **Uma biblioteca de canvas/whiteboard completa (`tldraw`, `react-flow`).**
  Resolvem pan/zoom infinito de fábrica, mas são construídas para desenho
  livre ou grafos de nós — trariam uma superfície grande de recursos não
  usados (conexões entre nós, desenho à mão livre, formas) para um
  problema mais simples (posicionar retângulos numa grade discreta).
  Rejeitada por trazer mais complexidade do que resolve aqui; fica como
  opção a reconsiderar se o pedido evoluir para algo mais livre que uma
  grade de células (ex.: widgets em qualquer ângulo/posição de pixel, não
  só em células).
- **Scroll nativo com `<div>` gigante e recentralização manual.** Descrita
  e rejeitada na seção "Decisão" acima, pelo risco de bugs de "salto" de
  tela ao crescer para trás.
