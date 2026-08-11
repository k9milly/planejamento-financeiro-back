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

/**
 * Rótulos e cores de cada tipo, usados nas etiquetas da tabela.
 *
 * Cada tipo mantém seu matiz nos dois temas — o que muda é a luminosidade:
 * fundo claro com texto escuro no tema claro, e o inverso no escuro.
 */
export const ESTILO_TIPO = {
  entrada: {
    rotulo: 'Entrada',
    classe:
      'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  },
  saida: {
    rotulo: 'Saída',
    classe: 'bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200',
  },
  guardado: {
    rotulo: 'Guardado',
    classe: 'bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200',
  },
  retirado: {
    rotulo: 'Retirado',
    classe: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  },
  rendimento: {
    rotulo: 'Rendimento',
    classe:
      'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200',
  },
} as const;
