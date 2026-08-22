import type { ReactNode } from 'react';

interface Props {
  titulo: string;
  children: ReactNode;
  /** Ocupa a largura toda — usado pelo container de lançamentos. */
  largo?: boolean;
  acao?: ReactNode;
  /**
   * Ocupa toda a altura disponível, rolando o conteúdo que sobrar.
   *
   * Usado pelo modo painel, onde quem manda na altura é a célula da grade:
   * sem isto, um card curto flutuaria no topo do bloco e um comprido
   * vazaria por baixo dele.
   */
  preencher?: boolean;
}

/** Container visual padrão. Todos os blocos da página de mês usam este. */
export function Card({
  titulo,
  children,
  largo = false,
  acao,
  preencher = false,
}: Props) {
  return (
    <section
      className={[
        'rounded-xl border border-roxo-100 bg-white shadow-sm dark:border-roxo-700 dark:bg-roxo-900',
        largo ? 'lg:col-span-3' : '',
        preencher ? 'flex h-full flex-col overflow-hidden' : '',
      ].join(' ')}
    >
      <header className="flex shrink-0 items-center justify-between border-b border-roxo-100 px-5 py-3 dark:border-roxo-700">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-roxo-400 dark:text-roxo-200">
          {titulo}
        </h2>
        {acao}
      </header>
      <div className={`p-5 ${preencher ? 'min-h-0 flex-1 overflow-auto' : ''}`}>
        {children}
      </div>
    </section>
  );
}

/** Par rótulo/valor usado dentro dos cards de totais. */
export function Linha({
  rotulo,
  valor,
  destaque = false,
  negativo = false,
}: {
  rotulo: string;
  valor: string;
  destaque?: boolean;
  negativo?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-sm text-roxo-500 dark:text-roxo-200">{rotulo}</span>
      <span
        className={[
          'tabular-nums',
          destaque ? 'text-lg font-semibold' : 'text-sm font-medium',
          negativo
            ? 'text-rose-600 dark:text-rose-400'
            : 'text-roxo-700 dark:text-roxo-50',
        ].join(' ')}
      >
        {valor}
      </span>
    </div>
  );
}

/** Classes compartilhadas pelos campos de formulário. */
export const CAMPO =
  'rounded-lg border border-roxo-100 px-3 py-2 text-sm focus:border-roxo-400 focus:outline-none dark:border-roxo-700 dark:focus:border-roxo-300';

/** Classes do botão primário. */
export const BOTAO =
  'rounded-lg bg-roxo-500 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400 disabled:opacity-50 dark:bg-roxo-400 dark:hover:bg-roxo-300';
