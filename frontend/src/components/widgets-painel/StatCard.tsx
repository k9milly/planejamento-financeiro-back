import type { ReactNode } from 'react';
import { moeda } from '../../lib/formato';

/**
 * Cartão de estatística única do modo painel: rótulo, valor grande, legenda
 * opcional. Sem barra de progresso — não existe "orçamento" para comparar
 * contra (ADR-0007); onde a imagem de referência mostrava uma meta, o
 * widget nasce mostrando só o valor real.
 */
export function StatCard({
  rotulo,
  valor,
  legenda,
  acento = 'violeta',
  negativo = false,
  filho,
}: {
  rotulo: string;
  /** Decimal cru (string, como a API manda) ou número — sempre passa por `moeda()`. */
  valor: string | number;
  legenda?: ReactNode;
  acento?: 'violeta' | 'rosa' | 'ciano' | 'ambar';
  negativo?: boolean;
  /** Conteúdo extra abaixo da legenda — ex.: lista curta, dropdown. */
  filho?: ReactNode;
}) {
  const texto = moeda(valor);

  return (
    <div
      className={`flex h-full flex-col justify-between rounded-2xl border border-white/10 bg-gradient-to-br ${GRADIENTES[acento]} p-4 text-white shadow-lg shadow-black/20`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-white/60">
        {rotulo}
      </p>
      <p
        className={`mt-1 truncate text-2xl font-semibold tabular-nums ${
          negativo ? 'text-rose-300' : 'text-white'
        }`}
      >
        {texto}
      </p>
      {legenda && <p className="mt-1 truncate text-xs text-white/50">{legenda}</p>}
      {filho}
    </div>
  );
}

const GRADIENTES: Record<'violeta' | 'rosa' | 'ciano' | 'ambar', string> = {
  violeta: 'from-violet-950 via-roxo-900 to-roxo-950',
  rosa: 'from-fuchsia-950 via-roxo-900 to-roxo-950',
  ciano: 'from-cyan-950 via-roxo-900 to-roxo-950',
  ambar: 'from-amber-950 via-roxo-900 to-roxo-950',
};
