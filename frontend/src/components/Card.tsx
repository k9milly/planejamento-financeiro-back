import type { ReactNode } from 'react';

interface Props {
  titulo: string;
  children: ReactNode;
  /** Ocupa a largura toda — usado pelo container de lançamentos. */
  largo?: boolean;
  acao?: ReactNode;
}

/** Container visual padrão. Todos os blocos da página de mês usam este. */
export function Card({ titulo, children, largo = false, acao }: Props) {
  return (
    <section
      className={`rounded-xl border border-slate-200 bg-white shadow-sm ${
        largo ? 'lg:col-span-3' : ''
      }`}
    >
      <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          {titulo}
        </h2>
        {acao}
      </header>
      <div className="p-5">{children}</div>
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
      <span className="text-sm text-slate-600">{rotulo}</span>
      <span
        className={[
          'tabular-nums',
          destaque ? 'text-lg font-semibold' : 'text-sm font-medium',
          negativo ? 'text-rose-600' : 'text-slate-900',
        ].join(' ')}
      >
        {valor}
      </span>
    </div>
  );
}
