/**
 * O layout do painel: onde cada widget fica no canvas, e como é guardado
 * (ADR-0006, ADR-0008).
 *
 * O backend trata `layout` como texto opaco — não valida o conteúdo (ver
 * `docs/CONTRATO-API.md`). Logo, quem valida é este módulo, na leitura: um
 * JSON corrompido, de uma versão antiga, ou citando um tipo de widget que
 * não existe mais não pode derrubar a tela. `interpretar` sempre devolve
 * algo renderizável.
 */

import { ID_WIDGETS, TAMANHO_PADRAO, type TipoWidget } from '../components/widgets/catalogo';

/** Tamanho de uma célula do canvas em pixels, no zoom 100% (ADR-0008/0009). */
export const CELL_W = 240;
export const CELL_H = 120;

/**
 * O canvas usa rolagem nativa do navegador (ADR-0009), não pan por
 * `transform` — a usuária pediu barra de scroll e zoom, no molde do Google
 * Sheets, e rolagem nativa dá as duas coisas de graça (a barra em si, e o
 * `scrollLeft`/`scrollTop` como base para o zoom). Isso troca a moldura
 * "sem borda nenhuma" do ADR-0008 por uma área grande, porém finita — mais
 * honesto, e mais fácil de se situar dentro dela do que um pan sem
 * referência nenhuma de posição.
 *
 * `ORIGEM_*` é quantas células ficam reservadas *antes* de (0,0) — é o que
 * permite `coluna`/`linha` negativos (um widget arrastado acima ou à
 * esquerda da origem) sem que a área de rolagem precise "crescer para
 * trás" (a mesma armadilha de scroll nativo que o ADR-0008 apontava:
 * `scrollLeft`/`scrollTop` não vão a negativo). `TOTAL_*` é o tamanho
 * inteiro da área rolável. Os números são generosos (48.000×48.000px no
 * zoom 100%) — não é "infinito" de verdade, mas nenhum uso real chega
 * perto da borda, no mesmo espírito do limite técnico que o Google Sheets
 * também tem (10 milhões de células) sem que ninguém perceba.
 */
export const ORIGEM_COL = 40;
export const ORIGEM_LIN = 40;
export const TOTAL_COLS = 200;
export const TOTAL_ROWS = 400;

/** Zoom em degraus, como o controle do Google Sheets — não contínuo, para o "encaixe" de célula ficar previsível. */
export const NIVEIS_ZOOM = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2] as const;
export const ZOOM_PADRAO = 1;

/** Posição e tamanho de um widget, em unidades de célula (podem ser negativas). */
export interface ItemLayout {
  /** Id da instância neste canvas — um mesmo tipo pode repetir (ADR-0008). */
  id: string;
  tipo: TipoWidget;
  coluna: number;
  linha: number;
  largura: number;
  altura: number;
  /** Configuração por instância — ex.: qual conta, como agrupar. */
  config?: Record<string, unknown>;
}

const CHAVE_LOCAL = 'planejamento:layout-dashboard';

/**
 * Layout de fábrica: o que a usuária vê antes de mexer em qualquer coisa.
 * Posicionado perto da origem, crescendo para baixo e para a direita —
 * nada obriga a ficar assim depois que ela arrasta algo.
 */
export const LAYOUT_PADRAO: ItemLayout[] = [
  { id: 'cabecalho', tipo: 'cabecalho-periodo', coluna: 0, linha: 0, largura: 12, altura: 1 },
  { id: 'saldo', tipo: 'saldo-atual', coluna: 0, linha: 1, largura: 4, altura: 2 },
  { id: 'contas', tipo: 'todas-contas', coluna: 4, linha: 1, largura: 4, altura: 2 },
  { id: 'lembrete', tipo: 'lembrete-dia', coluna: 8, linha: 1, largura: 4, altura: 2 },
  { id: 'receita', tipo: 'receita', coluna: 0, linha: 3, largura: 3, altura: 2 },
  { id: 'despesas-contas', tipo: 'despesas-contas', coluna: 3, linha: 3, largura: 3, altura: 2 },
  { id: 'investimentos-cartao', tipo: 'investimentos-cartao', coluna: 6, linha: 3, largura: 3, altura: 2 },
  { id: 'fatura', tipo: 'fatura-cartao', coluna: 9, linha: 3, largura: 3, altura: 2 },
  { id: 'patrimonio', tipo: 'patrimonio', coluna: 0, linha: 5, largura: 4, altura: 4 },
  { id: 'gastos-rosca', tipo: 'gastos-rosca', coluna: 4, linha: 5, largura: 4, altura: 4 },
  { id: 'detalhamento', tipo: 'detalhamento-despesas', coluna: 8, linha: 5, largura: 4, altura: 4 },
  { id: 'despesas-diarias', tipo: 'despesas-diarias', coluna: 0, linha: 9, largura: 6, altura: 3 },
  { id: 'saldo-inicial', tipo: 'saldo-inicial', coluna: 6, linha: 9, largura: 4, altura: 3 },
  { id: 'investimentos-tabela', tipo: 'investimentos-tabela', coluna: 10, linha: 9, largura: 6, altura: 3 },
  { id: 'calendario', tipo: 'calendario', coluna: 0, linha: 12, largura: 6, altura: 5 },
  { id: 'contas-recorrentes', tipo: 'contas-recorrentes', coluna: 6, linha: 12, largura: 6, altura: 5 },
  { id: 'despesas-tabela', tipo: 'despesas-tabela', coluna: 0, linha: 17, largura: 6, altura: 5 },
  { id: 'wishlist', tipo: 'wishlist', coluna: 6, linha: 17, largura: 4, altura: 4 },
  { id: 'lancamentos', tipo: 'lancamentos', coluna: 0, linha: 22, largura: 12, altura: 5 },
];

/** Converte o que veio do servidor/localStorage num layout confiável. */
export function interpretar(bruto: string | null): ItemLayout[] | null {
  if (!bruto) return null;
  try {
    const dados: unknown = JSON.parse(bruto);
    if (!Array.isArray(dados)) return null;

    const itens = dados.filter(ehItemValido);
    // Um layout que perdeu todos os widgets por incompatibilidade é pior que
    // nenhum: quem chama cai no padrão de fábrica em vez de mostrar vazio.
    return itens.length ? itens : null;
  } catch {
    return null;
  }
}

function ehItemValido(item: unknown): item is ItemLayout {
  if (typeof item !== 'object' || item === null) return false;
  const i = item as Record<string, unknown>;
  return (
    typeof i.id === 'string' &&
    typeof i.tipo === 'string' &&
    // Widget removido do catálogo numa versão nova: a instância é
    // descartada, o resto do layout sobrevive.
    (ID_WIDGETS as readonly string[]).includes(i.tipo) &&
    ['coluna', 'linha', 'largura', 'altura'].every(
      (k) => typeof i[k] === 'number' && Number.isFinite(i[k]),
    ) &&
    (i.config === undefined || (typeof i.config === 'object' && i.config !== null))
  );
}

export function serializar(layout: ItemLayout[]): string {
  return JSON.stringify(layout);
}

/**
 * Cópia local do layout.
 *
 * Existe para a tela abrir já arrumada, sem esperar a resposta do servidor
 * — e para toda solta de arrasto/redimensionamento parecer instantânea
 * (ADR-0006): grava na hora, sem round-trip de rede.
 */
export const layoutLocal = {
  ler: () => interpretar(localStorage.getItem(CHAVE_LOCAL)),
  gravar: (layout: ItemLayout[]) =>
    localStorage.setItem(CHAVE_LOCAL, serializar(layout)),
  limpar: () => localStorage.removeItem(CHAVE_LOCAL),
};

/** Retângulo em células, para checar sobreposição. */
interface Retangulo {
  coluna: number;
  linha: number;
  largura: number;
  altura: number;
}

function sobrepoe(a: Retangulo, b: Retangulo): boolean {
  return (
    a.coluna < b.coluna + b.largura &&
    b.coluna < a.coluna + a.largura &&
    a.linha < b.linha + b.altura &&
    b.linha < a.linha + a.altura
  );
}

/**
 * Se algum item do layout (fora `ignorarId`) ocupa células do retângulo
 * candidato. Usado para bloquear a solta de um arrasto/redimensionamento —
 * o canvas infinito não reorganiza vizinhos (ADR-0008).
 */
export function colide(
  layout: ItemLayout[],
  candidato: Retangulo,
  ignorarId: string,
): boolean {
  return layout.some((item) => item.id !== ignorarId && sobrepoe(item, candidato));
}

function idNovo(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `w${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Acrescenta uma instância nova na primeira célula livre a partir da
 * origem (varredura linha a linha) — não necessariamente abaixo de tudo,
 * como faria uma grade que só cresce para baixo.
 */
export function adicionar(layout: ItemLayout[], tipo: TipoWidget): ItemLayout[] {
  const { w: largura, h: altura } = TAMANHO_PADRAO[tipo];
  const LIMITE_LINHA = TOTAL_ROWS - ORIGEM_LIN - altura;
  const LIMITE_COLUNA = TOTAL_COLS - ORIGEM_COL - largura;

  for (let linha = 0; linha < LIMITE_LINHA; linha++) {
    for (let coluna = 0; coluna < LIMITE_COLUNA; coluna++) {
      const candidato = { coluna, linha, largura, altura };
      if (!colide(layout, candidato, '')) {
        return [...layout, { id: idNovo(), tipo, ...candidato }];
      }
    }
  }
  // Praticamente inalcançável (300×300 células cobertas antes de desistir);
  // cai no comportamento antigo, abaixo de tudo, como rede de segurança.
  const abaixoDeTudo = layout.reduce((maior, i) => Math.max(maior, i.linha + i.altura), 0);
  return [...layout, { id: idNovo(), tipo, coluna: 0, linha: abaixoDeTudo, largura, altura }];
}

export function remover(layout: ItemLayout[], id: string): ItemLayout[] {
  return layout.filter((item) => item.id !== id);
}

export function atualizarConfig(
  layout: ItemLayout[],
  id: string,
  config: Record<string, unknown>,
): ItemLayout[] {
  return layout.map((item) => (item.id === id ? { ...item, config } : item));
}

/**
 * Retângulo em pixels **dentro da área de rolagem** (zoom 100%, já somando
 * `ORIGEM_COL`/`ORIGEM_LIN`) — pronto para usar como `left`/`top`/`width`/
 * `height` do widget. Multiplicar por um zoom diferente de 1 é
 * responsabilidade de quem desenha (o wrapper inteiro escala via CSS
 * `transform: scale()`, não célula por célula).
 */
export function retanguloPx(item: ItemLayout) {
  return {
    left: (item.coluna + ORIGEM_COL) * CELL_W,
    top: (item.linha + ORIGEM_LIN) * CELL_H,
    width: item.largura * CELL_W,
    height: item.altura * CELL_H,
  };
}

/** Limita coluna/linha para o widget não ser arrastado/redimensionado para fora da área rolável. */
export function limitarRetangulo(r: {
  coluna: number;
  linha: number;
  largura: number;
  altura: number;
}) {
  return {
    ...r,
    coluna: Math.max(-ORIGEM_COL, Math.min(r.coluna, TOTAL_COLS - ORIGEM_COL - r.largura)),
    linha: Math.max(-ORIGEM_LIN, Math.min(r.linha, TOTAL_ROWS - ORIGEM_LIN - r.altura)),
  };
}

/** Centro (em células) do conjunto de widgets — usado pelo botão "Centralizar". */
export function centroide(layout: ItemLayout[]): { coluna: number; linha: number } {
  if (layout.length === 0) return { coluna: 0, linha: 0 };
  const somaX = layout.reduce((s, i) => s + i.coluna + i.largura / 2, 0);
  const somaY = layout.reduce((s, i) => s + i.linha + i.altura / 2, 0);
  return { coluna: somaX / layout.length, linha: somaY / layout.length };
}
