import { Moldura } from './Moldura';
import { moeda } from '../../lib/formato';
import type { Categoria, Conta, Lancamento, ResumoMes } from '../../types/api';

type AgruparPor = 'categoria' | 'conta';

/**
 * Detalhamento das despesas do mês, em barras — por categoria (reaproveita
 * `gastos_por_categoria`, mesma fonte do widget "para onde meu dinheiro
 * vai") ou por conta (calculado no cliente a partir de `lancamentos`, sem
 * endpoint novo). A visão é uma configuração da mesma instância, não um
 * segundo tipo de widget (ver spec, seção 3).
 */
export function DetalhamentoDespesas({
  mes,
  categorias,
  contas,
  lancamentos,
  agruparPor,
  aoMudarAgrupamento,
}: {
  mes: ResumoMes;
  categorias: Categoria[];
  contas: Conta[];
  lancamentos: Lancamento[];
  agruparPor: AgruparPor;
  aoMudarAgrupamento: (valor: AgruparPor) => void;
}) {
  const linhas =
    agruparPor === 'categoria'
      ? mes.gastos_por_categoria.map((g) => ({
          nome: g.categoria,
          valor: Number(g.total),
          cor: categorias.find((c) => c.nome === g.categoria)?.cor,
        }))
      : porConta(lancamentos, contas);

  const maior = linhas.length ? Math.max(...linhas.map((l) => l.valor)) : 0;

  return (
    <Moldura
      titulo="Detalhamento das despesas"
      acao={
        <div className="flex overflow-hidden rounded-md border border-white/10 text-xs">
          {(['categoria', 'conta'] as const).map((v) => (
            <button
              key={v}
              onClick={() => aoMudarAgrupamento(v)}
              className={`px-2 py-0.5 ${
                agruparPor === v ? 'bg-white/20 text-white' : 'text-white/50 hover:bg-white/10'
              }`}
            >
              {v === 'categoria' ? 'Categoria' : 'Conta'}
            </button>
          ))}
        </div>
      }
    >
      {linhas.length === 0 ? (
        <p className="text-white/40">Nenhuma saída registrada.</p>
      ) : (
        <ul className="space-y-2">
          {linhas.map((l) => (
            <li key={l.nome}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="truncate text-white/70" style={l.cor ? { color: l.cor } : undefined}>
                  {l.nome}
                </span>
                <span className="shrink-0 tabular-nums text-white/80">{moeda(l.valor)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-fuchsia-400 to-cyan-400"
                  style={{ width: maior ? `${(l.valor / maior) * 100}%` : '0%' }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Moldura>
  );
}

function porConta(lancamentos: Lancamento[], contas: Conta[]) {
  const totais = new Map<number, number>();
  for (const l of lancamentos) {
    if (l.tipo !== 'saida') continue;
    totais.set(l.conta_id, (totais.get(l.conta_id) ?? 0) + Number(l.valor));
  }
  return [...totais.entries()]
    .map(([contaId, valor]) => ({
      nome: contas.find((c) => c.id === contaId)?.nome ?? '—',
      valor,
      cor: contas.find((c) => c.id === contaId)?.cor,
    }))
    .sort((a, b) => b.valor - a.valor);
}
