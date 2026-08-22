import { Card } from './Card';
import { moeda } from '../lib/formato';
import type { Categoria, ResumoMes } from '../types/api';

interface Props {
  mes: ResumoMes;
  categorias: Categoria[];
  /** No modo painel, quem define a altura é a célula da grade. */
  preencher?: boolean;
}

/**
 * Container de gastos por categoria, com barra proporcional.
 *
 * A barra usa largura relativa ao maior gasto do mês (e não ao total), porque
 * comparar categorias entre si é o que interessa aqui — o percentual sobre o
 * total fica no número ao lado.
 */
export function GastosPorCategoria({ mes, categorias, preencher }: Props) {
  const gastos = mes.gastos_por_categoria;
  const maior = gastos.length ? Number(gastos[0].total) : 0;
  const corDe = (nome: string) => categorias.find((c) => c.nome === nome)?.cor;

  return (
    <Card titulo="Gastos por categoria" preencher={preencher}>
      {gastos.length === 0 ? (
        <p className="text-sm text-roxo-300">Nenhuma saída registrada.</p>
      ) : (
        <ul className="space-y-3">
          {gastos.map((gasto) => (
            <li key={gasto.categoria}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span
                  className="text-roxo-600 dark:text-roxo-100"
                  style={corDe(gasto.categoria) ? { color: corDe(gasto.categoria) } : undefined}
                >
                  {gasto.categoria}
                </span>
                <span className="tabular-nums font-medium text-roxo-700 dark:text-roxo-50">
                  {moeda(gasto.total)}
                  <span className="ml-2 text-xs font-normal text-roxo-300">
                    {gasto.percentual.toFixed(0)}%
                  </span>
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-roxo-100 dark:bg-roxo-700">
                <div
                  className="h-full rounded-full bg-roxo-400"
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
