import { Card } from './Card';
import { moeda } from '../lib/formato';
import type { ResumoMes } from '../types/api';

/**
 * Container de gastos por categoria, com barra proporcional.
 *
 * A barra usa largura relativa ao maior gasto do mês (e não ao total), porque
 * comparar categorias entre si é o que interessa aqui — o percentual sobre o
 * total fica no número ao lado.
 */
export function GastosPorCategoria({ mes }: { mes: ResumoMes }) {
  const gastos = mes.gastos_por_categoria;
  const maior = gastos.length ? Number(gastos[0].total) : 0;

  return (
    <Card titulo="Gastos por categoria">
      {gastos.length === 0 ? (
        <p className="text-sm text-slate-400">Nenhuma saída registrada.</p>
      ) : (
        <ul className="space-y-3">
          {gastos.map((gasto) => (
            <li key={gasto.categoria}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-slate-700">{gasto.categoria}</span>
                <span className="tabular-nums font-medium text-slate-900">
                  {moeda(gasto.total)}
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    {gasto.percentual.toFixed(0)}%
                  </span>
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-slate-400"
                  style={{
                    width: maior ? `${(Number(gasto.total) / maior) * 100}%` : '0%',
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
