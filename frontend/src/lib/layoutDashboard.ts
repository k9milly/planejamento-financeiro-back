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

/** Tamanho de uma célula do canvas, em pixels (ADR-0008). */
export const CELL_W = 240;
export const CELL_H = 120;

/**
 * Limite técnico honesto (ADR-0008): não é um limite de produto, é o teto
 * real de pixels que alguns motores de navegador conseguem posicionar. O
 * usuário nunca chega perto — é o mesmo tipo de limite que o Google Sheets
 * tem (10 milhões de células) sem que ninguém perceba como "não infinito".
 *
 * Implementação simplificada em relação à letra do ADR: em vez de rastrear
 * um retângulo `(colMin, colMax, linMin, linMax)` que cresce sob demanda
 * conforme o pan se aproxima da borda, o pan é livre dentro deste limite
 * fixo desde o início. O resultado observável é idêntico — "rolar em
 * qualquer direção nunca esbarra numa borda visível" —, porque o limite é
 * grande demais para ser alcançável, e o código fica bem mais simples sem
 * o rastreamento incremental.
 */
export const LIMITE_PX = 24_000_000;

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
  const LIMITE_BUSCA = 300;

  for (let linha = 0; linha < LIMITE_BUSCA; linha++) {
    for (let coluna = 0; coluna < LIMITE_BUSCA; coluna++) {
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

/** Retângulo em pixels do canvas (antes do pan), para posicionar e para colisão de arrasto. */
export function retanguloPx(item: ItemLayout) {
  return {
    left: item.coluna * CELL_W,
    top: item.linha * CELL_H,
    width: item.largura * CELL_W,
    height: item.altura * CELL_H,
  };
}

/** Centro (em células) do conjunto de widgets — usado pelo botão "Centralizar". */
export function centroide(layout: ItemLayout[]): { coluna: number; linha: number } {
  if (layout.length === 0) return { coluna: 0, linha: 0 };
  const somaX = layout.reduce((s, i) => s + i.coluna + i.largura / 2, 0);
  const somaY = layout.reduce((s, i) => s + i.linha + i.altura / 2, 0);
  return { coluna: somaX / layout.length, linha: somaY / layout.length };
}
