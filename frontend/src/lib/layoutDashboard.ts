/**
 * O layout do painel: onde cada bloco fica, e como ele é guardado (ADR-0006).
 *
 * O backend trata `layout` como texto opaco — não valida o conteúdo (ver
 * `docs/CONTRATO-API.md`). Logo, quem valida é este módulo, na leitura: um
 * JSON corrompido, de uma versão antiga, ou com um widget que não existe mais
 * não pode derrubar a tela. `interpretar` sempre devolve algo renderizável.
 */

import { ID_WIDGETS, TAMANHO_PADRAO, type IdWidget } from '../components/widgets/catalogo';

/** Posição e tamanho de um bloco, em unidades de grade. */
export interface ItemLayout {
  /** Id do widget no catálogo. É a chave do `react-grid-layout`. */
  i: IdWidget;
  x: number;
  y: number;
  w: number;
  h: number;
}

const CHAVE_LOCAL = 'planejamento:layout-painel';

/**
 * Layout de fábrica: o que a usuária vê antes de arrastar qualquer coisa.
 *
 * A ordem segue a leitura de cima para baixo — primeiro "quanto eu tenho",
 * depois "para onde foi", depois "o que ainda vem". A grade tem 12 colunas.
 */
export const LAYOUT_PADRAO: ItemLayout[] = [
  { i: 'saldo', x: 0, y: 0, w: 4, h: 5 },
  { i: 'patrimonio', x: 4, y: 0, w: 4, h: 5 },
  { i: 'fatura-cartao', x: 8, y: 0, w: 4, h: 5 },
  { i: 'gastos-rosca', x: 0, y: 5, w: 4, h: 6 },
  { i: 'gastos-tabela', x: 4, y: 5, w: 4, h: 6 },
  { i: 'despesas-diarias', x: 8, y: 5, w: 4, h: 6 },
  { i: 'calendario', x: 0, y: 11, w: 6, h: 7 },
  { i: 'contas-recorrentes', x: 6, y: 11, w: 6, h: 7 },
  { i: 'saldo-inicial', x: 0, y: 18, w: 4, h: 4 },
  { i: 'wishlist', x: 4, y: 18, w: 8, h: 4 },
  { i: 'lancamentos', x: 0, y: 22, w: 12, h: 8 },
];

/** Converte o que veio do servidor/localStorage num layout confiável. */
export function interpretar(bruto: string | null): ItemLayout[] | null {
  if (!bruto) return null;
  try {
    const dados: unknown = JSON.parse(bruto);
    if (!Array.isArray(dados)) return null;

    const itens = dados.filter(ehItemValido);
    // Um layout que perdeu todos os blocos por incompatibilidade é pior que
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
    typeof i.i === 'string' &&
    // Widget removido do catálogo numa versão nova: o bloco é descartado, o
    // resto do layout sobrevive.
    (ID_WIDGETS as readonly string[]).includes(i.i) &&
    ['x', 'y', 'w', 'h'].every((k) => typeof i[k] === 'number' && Number.isFinite(i[k]))
  );
}

export function serializar(layout: ItemLayout[]): string {
  // Só os cinco campos do contrato: o react-grid-layout devolve os itens com
  // campos internos (`moved`, `static`) que não têm por que ser persistidos.
  return JSON.stringify(
    layout.map(({ i, x, y, w, h }) => ({ i, x, y, w, h })),
  );
}

/**
 * Cópia local do layout.
 *
 * Existe para a tela abrir já arrumada, sem esperar a resposta do servidor —
 * e para não perder o arranjo se o `PUT` falhar por rede.
 */
export const layoutLocal = {
  ler: () => interpretar(localStorage.getItem(CHAVE_LOCAL)),
  gravar: (layout: ItemLayout[]) =>
    localStorage.setItem(CHAVE_LOCAL, serializar(layout)),
  limpar: () => localStorage.removeItem(CHAVE_LOCAL),
};

/** Widgets do catálogo que ainda não estão na tela — o que o "+" oferece. */
export function widgetsDisponiveis(layout: ItemLayout[]): IdWidget[] {
  const naTela = new Set(layout.map((item) => item.i));
  return ID_WIDGETS.filter((id) => !naTela.has(id));
}

/** Acrescenta um bloco no fim da grade, no tamanho padrão dele. */
export function adicionar(layout: ItemLayout[], id: IdWidget): ItemLayout[] {
  const abaixoDeTudo = layout.reduce((maior, i) => Math.max(maior, i.y + i.h), 0);
  return [...layout, { i: id, x: 0, y: abaixoDeTudo, ...TAMANHO_PADRAO[id] }];
}
