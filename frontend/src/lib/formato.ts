/** Formatação de valores e datas em pt-BR. */

const MOEDA = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

/** "1234.56" -> "R$ 1.234,56" */
export function moeda(valor: string | number): string {
  return MOEDA.format(typeof valor === 'string' ? Number(valor) : valor);
}

/** "2026-04-06" -> "06/04". O ano é redundante dentro de uma página de mês. */
export function diaMes(iso: string): string {
  const [, mes, dia] = iso.split('-');
  return `${dia}/${mes}`;
}

export function ehNegativo(valor: string): boolean {
  return Number(valor) < 0;
}

export const NOMES_MESES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
] as const;

/** Rótulos e cores de cada tipo, usados nas etiquetas da tabela. */
export const ESTILO_TIPO = {
  entrada: { rotulo: 'Entrada', classe: 'bg-emerald-100 text-emerald-800' },
  saida: { rotulo: 'Saída', classe: 'bg-rose-100 text-rose-800' },
  guardado: { rotulo: 'Guardado', classe: 'bg-sky-100 text-sky-800' },
  retirado: { rotulo: 'Retirado', classe: 'bg-amber-100 text-amber-800' },
  rendimento: { rotulo: 'Rendimento', classe: 'bg-violet-100 text-violet-800' },
} as const;
