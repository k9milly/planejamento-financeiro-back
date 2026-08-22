# Spec — Modo painel: alternância, canvas infinito e catálogo de widgets

Cobre a segunda rodada de mudanças pedidas, com a correção feita na
terceira rodada (canvas infinito no lugar da grade responsiva original —
ver ADR-0008). As decisões de arquitetura por trás de cada parte estão nos
ADRs 0004–0008, em `docs/adr/`; este documento é o "o quê".

> **Nota de revisão (rodada 3):** a seção 2 abaixo foi reescrita para
> refletir o ADR-0008 (canvas infinito, `dnd-kit`) no lugar do ADR-0005
> (grade responsiva, `react-grid-layout`), que ela descrevia originalmente.
>
> **Nota de revisão (rodada 4):** testado de verdade, faltava barra de
> rolagem (referência de posição) e zoom. O ADR-0009 troca o mecanismo de
> rolagem do canvas — nativa do navegador, não mais `transform:
> translate()` — e acrescenta zoom em degraus. Os dois parágrafos de "O
> canvas", abaixo, foram atualizados; o resto da seção 2 (coordenadas com
> sinal, colisão bloqueada, virtualização, modo de edição) não mudou. As
> seções 1 e 3 também não mudaram.

Terminologia usada pelo usuário, mantida ao longo do documento: **modo
planilha** (interface atual, inalterada) e **modo painel** (a interface
nova, no molde da imagem de referência anexada ao pedido).

---

## 1. Alternância entre os dois modos

### `lib/modoVisual.ts` (novo, no molde de `lib/tema.ts`)

```ts
export type ModoVisual = 'planilha' | 'painel';
const CHAVE = 'planejamento:modo-visual';

export function useModoVisual() {
  const [modo, setModo] = useState<ModoVisual>(() => {
    const salvo = localStorage.getItem(CHAVE);
    return salvo === 'painel' ? 'painel' : 'planilha';
  });

  useEffect(() => localStorage.setItem(CHAVE, modo), [modo]);

  return { modo, alternar: () => setModo(m => m === 'planilha' ? 'painel' : 'planilha') };
}
```

### `App.tsx`

Reestruturação (sem mudar o que já funciona):

- Todo o `<div className="min-h-screen ...">` que hoje é o corpo de
  `App.tsx` (cabeçalho, navegação de meses, grid de containers) migra
  **sem alterações de comportamento** para `components/ModoPlanilha.tsx`,
  recebendo por props os dados que `App.tsx` já carrega (`resumo`,
  `lancamentos`, `contas`, `gastosFixos`, `desejos`, `anoAtual`, `mesAtual`,
  os `acao(...)` já montados) — uma extração mecânica, não uma reescrita.
- `App.tsx` passa a decidir entre `<ModoPlanilha ... />` e
  `<ModoPainel ... />` com base em `useModoVisual()`.
- O botão de alternância entra no cabeçalho comum aos dois modos — como o
  cabeçalho hoje só existe dentro do que virou `ModoPlanilha`, um pequeno
  cabeçalho compartilhado (título do app, seletor de ano, o próprio botão
  de modo, `BotaoTema`, "Sair") sobe para `App.tsx`, e cada modo desenha
  só o que é específico dele abaixo (navegação por mês no modo planilha;
  nada equivalente no modo painel, que mostra o mês corrente inteiro
  numa tela só, com os próprios controles de período dentro do widget de
  cabeçalho — ver seção 3).

### Critérios de aceite

- Usuário que nunca trocou de modo não percebe nenhuma diferença — a tela
  é pixel-a-pixel a mesma de hoje (modo planilha continua padrão).
- Alternar de modo preserva o ano/mês selecionado.
- Recarregar a página mantém o último modo escolhido.

---

## 2. Canvas infinito (só no modo painel)

Ver ADR-0008 e ADR-0009 para o raciocínio completo. Esta seção é o "o quê"
resultante.

### O canvas

Uma área rolável nativa do navegador (`overflow: auto`), grande — 200
colunas × 400 linhas no zoom 100% — mas finita (ADR-0009; era `transform:
translate()` sem borda nenhuma nas duas primeiras versões desta spec).
Rola pela barra de rolagem, pela roda do mouse/trackpad ou por toque, como
qualquer área com scroll. Coordenadas de célula negativas (widget acima ou
à esquerda da origem) continuam possíveis: um deslocamento de origem fixo
(`ORIGEM_COL`/`ORIGEM_LIN`) garante que `scrollLeft`/`scrollTop` — que não
aceitam valor negativo — nunca precisem ser negativos para isso.

Um controle de zoom no canto inferior direito (`− 100% +`, no molde do
Google Sheets) escala tudo junto — texto, widgets, espaçamento — em
degraus fixos (25% a 200%). Trocar de degrau mantém o ponto do canvas que
está no centro da tela, para o zoom não "chutar" a visão para outro lugar.

Um fundo com um padrão sutil de grade (linhas finas marcando as células)
reforça visualmente a metáfora de planilha.

### Modo de visualização vs. modo de edição

Por padrão, o modo painel abre em **modo de visualização**: os widgets
não podem ser arrastados nem redimensionados (evita mover um bloco sem
querer ao rolar a tela para navegar). Rolar continua funcionando
normalmente nos dois modos — só a manipulação dos widgets é que fica
travada fora do modo de edição. Um botão "Editar layout" entra em **modo
de edição**, que:

- habilita arrastar (`dnd-kit`) e redimensionar (alça no canto de cada
  widget) — ver ADR-0008;
- mostra um botão "+" flutuante que abre o catálogo de widgets
  disponíveis, para adicionar um que foi removido;
- mostra um "✕" no canto de cada widget, para removê-lo do layout (não
  apaga dado nenhum — só tira o widget da tela; pode ser adicionado de
  volta);
- mostra os botões "Salvar layout" e "Restaurar padrão" (ver ADR-0006 e
  "Confirmação de salvamento" abaixo);
- mostra um botão fixo "Centralizar" (ícone de mira), que rola de volta
  até enquadrar todos os widgets existentes — sem ele, é fácil rolar
  demais numa direção numa área grande e perder a referência de onde os
  widgets estão.

Sair do modo de edição (botão "Concluir") volta ao modo de visualização
travado — o estado de edição em si **não** precisa ser persistido, só o
layout resultante.

### Schema do layout

```ts
interface ItemLayout {
  id: string;          // instância do widget neste canvas — um tipo pode repetir
  tipo: TipoWidget;     // ver catálogo, seção 3
  coluna: number; linha: number;              // inteiros, podem ser negativos
  largura: number; altura: number;            // em número de células
  config?: Record<string, unknown>; // por widget — ex.: qual conta, no widget "saldo de uma conta"
}
type LayoutDashboard = ItemLayout[];
```

Célula padrão: 240×120px (constante configurável, não exposta ao usuário
nesta v1). Widgets sempre ocupam um número inteiro de células — arrastar e
redimensionar fazem *snap* para a grade de células, não para pixels
livres, reforçando a metáfora de planilha.

### Tamanho da área rolável (ADR-0009)

A área é grande, mas finita e visível — a barra de rolagem mostra isso
honestamente, ao contrário da tentativa "infinita" da versão anterior
desta spec, que também tinha um teto técnico, só que escondido. 200
colunas × 400 linhas no zoom 100% (48.000×48.000px) é generoso o bastante
para que nenhum uso real chegue perto da borda — mas, se chegar, a barra
de rolagem simplesmente para, como em qualquer documento com scroll (o
mesmo tipo de limite que o Google Sheets tem, com 10 milhões de células,
sem que ninguém perceba).

### Virtualização

Só widgets cujo retângulo intersecta a janela de visualização atual (mais
uma margem) são montados no DOM, com base em `scrollLeft`/`scrollTop`.
Isso é necessário — diferente da grade responsiva antiga, que cabia
inteira na tela por definição, este canvas pode acumular widgets muito
além do que está visível a qualquer momento.

### Colisão: bloqueada, sem reflow automático

Soltar um widget sobre células já ocupadas por outro é rejeitado — ele
volta para a última posição válida (pequena animação de retorno). Não há
reorganização automática dos vizinhos (o "empurrar" que uma grade
responsiva compacta precisa não se aplica aqui: numa área deste tamanho, o
usuário sempre tem espaço livre ao lado).

### Carregamento e persistência (fluxo completo)

1. Ao entrar no modo painel: `GET /preferencias/layout-dashboard`.
2. Se veio um layout: usa ele (e atualiza o cache local).
3. Se veio vazio: usa o cache local (`localStorage`), se existir.
4. Se nenhum dos dois existir: usa o **layout padrão de fábrica** —
   uma disposição inicial fixa, definida no código, inspirada na imagem
   de referência (ver seção 3 para o tamanho padrão sugerido de cada
   widget), posicionada perto da origem `(0, 0)`.
5. Toda mudança de posição/tamanho, durante o modo de edição, grava
   imediatamente no `localStorage`.
6. "Salvar layout" envia o layout atual para
   `PUT /preferencias/layout-dashboard`.
7. "Restaurar padrão" apaga a cópia local e a do servidor, recarrega o
   layout de fábrica, e exige um novo "Salvar layout" para persistir a
   volta ao padrão (evita apagar sem querer o layout salvo antes de ter
   certeza).

### Confirmação de salvamento

Clicar em "Salvar layout" mostra uma confirmação (ex.: "Layout salvo",
num toast/badge pequeno perto do botão) que **desaparece sozinha depois de
alguns segundos** (sugestão: 3s, via `setTimeout` limpando o estado da
mensagem — cancelado se o componente desmontar ou se um novo "Salvar" for
clicado antes de o anterior sumir, para não empilhar timers). A mensagem
não é um estado permanente da tela — é um retorno pontual daquele clique,
igual a qualquer confirmação transitória (o mesmo padrão que qualquer
"salvo com sucesso" de formulário deveria seguir, e que faltou
especificar na primeira versão desta spec).

### Adicionar/remover widget

O catálogo (botão "+" no modo de edição) lista os tipos disponíveis com
uma prévia pequena. Adicionar cria um novo `ItemLayout` na primeira célula
livre a partir da origem, no tamanho padrão daquele tipo. Widgets do mesmo
tipo podem coexistir (ex.: dois widgets "saldo de uma conta", cada um
configurado para uma conta diferente, via `config.conta_id`).

### Critérios de aceite

- Rolar em qualquer direção mostra a barra de rolagem nativa do
  navegador nos dois eixos, e não esbarra numa borda visível dentro do
  uso normal (a área é grande demais para isso — ver "Tamanho da área
  rolável").
- Um widget pode ser colocado em coordenadas negativas (acima/à esquerda
  da origem) sem tratamento especial.
- Soltar um widget sobre outro já existente não move nenhum dos dois —
  o widget solto volta para onde estava.
- Sair da área visível e clicar em "Centralizar" traz todos os widgets de
  volta à tela.
- "Layout salvo" desaparece sozinho — nunca fica preso na tela depois de
  clicar em "Salvar layout" mais de uma vez seguida.
- Em tela estreita (celular), o modo de edição fica desabilitado — rolar
  por toque continua funcionando para navegar entre os widgets já
  posicionados, mas redimensionar por alça e o catálogo de adicionar
  ficam fora de escopo nesta v1 (ver "fora de escopo").
- O controle de zoom (`− 100% +`) escala tudo junto e mantém o ponto
  central da tela ao trocar de degrau.

---

## 3. Catálogo de widgets (v1)

Nome do widget como aparece na imagem de referência → dado de origem →
tamanho padrão (em células do canvas — ver seção 2) → observação.

| Widget | Dado de origem | Tam. padrão | Observação |
| --- | --- | --- | --- |
| Cabeçalho do período | `anoAtual`/`mesAtual`, já selecionados em `App.tsx` | 12×1 | Sem intervalo de datas livre nesta v1 — mês calendário, como o resto do app. |
| Saldo atual | `ResumoMesOut.saldo` | 4×2 | Barra de progresso é decorativa (não há "orçamento" para comparar — ver ADR-0007); mostra só o valor. |
| Todas as contas / saldo total | `ResumoAnoOut.por_conta`, `saldo_final` | 4×2 | Dropdown filtra a lista por conta; reaproveita dado já existente. |
| Lembrete do dia | Vencimentos de `GastoFixo` no dia de hoje + fatura de cartão vencendo hoje (rodada anterior) | 4×2 | Cálculo client-side sobre dado já carregado — sem endpoint novo. |
| Receita (cartão) | Soma de `entradas` do `ResumoMesOut` | 3×2 | Sem categoria/meta — ver ADR-0007. |
| Despesas & contas (cartão) | Soma de `saidas` + gastos fixos pendentes | 3×2 | — |
| Dívidas (cartão) | — | 3×2 | **Fora de escopo v1** — sem dado de origem; widget nasce oculto do catálogo até existir o domínio (ver ADR-0007). |
| Investimentos (cartão) | `guardado_no_mes`/`guardado_acumulado` | 3×2 | Aproximação: mostra o "guardado", não uma lista de investimentos por linha. |
| Patrimônio líquido total | Soma de `saldo + guardado` de todas as contas correntes | 4×4 | Mesmo cálculo que já aparece em `GerenciadorContas`. |
| Despesas diárias reais | `Lancamento[]` do mês, tipo `saida`, agrupado por dia no cliente | 6×3 | Novo cálculo, sem endpoint novo — os lançamentos do mês já são buscados hoje. |
| Para onde meu dinheiro vai | `ResumoMesOut.gastos_por_categoria` | 4×4 | Reaproveita exatamente o dado de `GastosPorCategoria.tsx`, só que como rosca em vez de lista. |
| Detalhamento real das despesas | `ResumoMesOut.gastos_por_categoria` (ou por conta) | 4×4 | Mesma fonte da anterior; visão alternativa (por conta) fica como variação de configuração do widget, não um segundo tipo. |
| Calendário | `CalendarioVencimentos` (gastos fixos) + vencimento de fatura de cartão (rodada anterior) | 6×5 | Reaproveita o componente já existente, só troca a casca visual (cores do modo painel). |
| Saldo inicial | `Ano.saldos_iniciais` | 4×3 | Dado já existe, tabela só é lida (edição continua pelo fluxo atual). |
| Resumo do plano de contas (previsto) | — | — | **Fora de escopo v1** — depende de orçamento (ADR-0007). |
| Despesas por categoria (tabela) | `ResumoMesOut.gastos_por_categoria` | 6×5 | Mesmo dado do widget "para onde meu dinheiro vai", em formato de tabela; sem coluna de orçamento. |
| Contas recorrentes | `GastoFixo[]` do mês | 6×5 | Quase 1:1 com `GastosFixos.tsx` — "Real" existe (`valor`), "Orçamento" não (ver ADR-0007); "Pagar?" reaproveita o toggle já existente. |
| Dívidas (tabela) | — | — | **Fora de escopo v1** (ADR-0007). |
| Investimentos (tabela) | `guardado` por conta | 6×3 | Versão simplificada: total guardado por conta, sem histórico de aportes individuais. |
| Lançamentos do mês | `Lancamento[]` do mês | 12×5 | Reaproveita `TabelaLancamentos.tsx` como está. |
| Wishlist | `Desejo[]` | 4×4 | Reaproveita `Wishlist.tsx` como está. |
| Fatura de cartão em aberto | `por_cartao` (rodada anterior — saldo inteligente) | 4×3 | Depende da spec "Saldo inteligente" já entregue; ver plano de implementação para a ordem entre as duas rodadas. |

### Visual do modo painel

A imagem de referência usa um tema escuro, roxo/violeta de fundo, com
gradientes rosa/ciano nos cartões de destaque e gráficos de rosca/área
coloridos — bem diferente da paleta clara "roxo" que o app usa hoje (que
continua intacta no modo planilha). Recomenda-se, na hora de implementar:

- Uma paleta própria do modo painel (não precisa ser idêntica à
  imagem, mas na mesma família: fundo escuro, cartões com leve gradiente,
  acentos vibrantes para diferenciar categorias/séries).
- Usar a skill `dataviz` deste workspace para os gráficos novos (rosca,
  sparkline de área) — ela já traz uma fórmula de cor validada para
  série categórica e sequencial, evitando escolher cores ad hoc que não
  funcionam bem nos dois temas.
- Biblioteca de gráficos: nenhuma existe hoje no frontend (ver
  `package.json`). Recharts é a escolha natural — é a mais comum no
  ecossistema React, cobre rosca/área/linha sem configuração pesada, e
  compõe bem com os princípios da skill `dataviz` citada acima.

### Critérios de aceite

- Cada widget da tabela acima, quando adicionado ao layout, mostra o dado
  correto para o mês/ano selecionado em `App.tsx` — sem busca própria de
  dado.
- Widgets marcados "fora de escopo v1" não aparecem no catálogo de
  adicionar — evita a pessoa tentar usar algo que ainda não existe.
- Nenhum widget novo exige um endpoint novo além dos dois de
  `preferencias/layout-dashboard` (ADR-0006) — todo o resto reaproveita a
  API que já existe (incluindo a da rodada anterior, cartão/fatura).

---

## Fora de escopo (explicitamente)

- Orçamento/meta por categoria, e toda coluna "Orçamento"/"Restante" que
  depende dele (ADR-0007).
- Dívidas e investimentos como entidades com suas próprias linhas
  (parcela, aporte, rendimento individual).
- Redimensionar widgets por alça em tela estreita (rolar por toque, sim,
  funciona — ver critérios de aceite da seção 2).
- Zoom contínuo (pinça no trackpad, `Ctrl`+roda) — os degraus fixos do
  controle `− 100% +` cobrem o pedido (ADR-0009).
- Intervalo de datas livre no cabeçalho do período (a v1 usa sempre o mês
  calendário corrente, como o resto do app).
- Aplicar o mesmo canvas infinito ao modo planilha — o motor (ADR-0008) é
  o mesmo se isso for pedido depois, mas não é construído nesta rodada.
