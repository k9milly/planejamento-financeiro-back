import type { ReactNode } from 'react';

/** Moldura escura padrão dos widgets novos do painel (sem título de card à parte). */
export function Moldura({
  titulo,
  acao,
  children,
}: {
  titulo: string;
  acao?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-roxo-900/80 p-4 text-white shadow-lg shadow-black/20">
      <div className="mb-2 flex shrink-0 items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-white/60">
          {titulo}
        </p>
        {acao}
      </div>
      <div className="min-h-0 flex-1 overflow-auto text-sm">{children}</div>
    </div>
  );
}
