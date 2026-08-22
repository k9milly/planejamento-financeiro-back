import { NOMES_MESES } from '../../lib/formato';

/**
 * Faixa decorativa com o mês/ano selecionados. Sem seletor de intervalo
 * livre nesta v1 — o painel sempre segue o mês calendário corrente escolhido
 * na planilha (ver "Fora de escopo" na spec).
 */
export function CabecalhoPeriodo({ ano, mes }: { ano: number; mes: number }) {
  return (
    <div className="flex h-full items-center justify-between rounded-2xl border border-white/10 bg-gradient-to-r from-fuchsia-950 via-roxo-900 to-cyan-950 px-5 text-white shadow-lg shadow-black/20">
      <span className="text-lg font-semibold tracking-tight">
        {NOMES_MESES[mes - 1]} de {ano}
      </span>
      <span className="text-xs text-white/50">Painel</span>
    </div>
  );
}
