import { Card, Linha } from './Card';
import { moeda, NOMES_MESES } from '../lib/formato';
import type { ResumoAno } from '../types/api';

/**
 * Container "Total guardado": quanto foi guardado em cada mês, mais o total.
 *
 * Meses sem movimentação na reserva são omitidos — listar doze linhas zeradas
 * esconderia as que importam.
 */
export function TotalGuardado({
  resumo,
  preencher,
}: {
  resumo: ResumoAno;
  /** No modo painel, quem define a altura é a célula da grade. */
  preencher?: boolean;
}) {
  const comMovimento = resumo.meses.filter(
    (m) => Number(m.guardado_no_mes) !== 0,
  );
  const reservas = resumo.por_conta.filter((c) => Number(c.guardado) !== 0);

  return (
    <Card titulo="Total guardado" preencher={preencher}>
      <div className="divide-y divide-roxo-100 dark:divide-roxo-700">
        {comMovimento.length === 0 ? (
          <p className="py-2 text-sm text-roxo-300">
            Nenhum valor guardado neste ano ainda.
          </p>
        ) : (
          comMovimento.map((mes) => (
            <Linha
              key={mes.mes}
              rotulo={NOMES_MESES[mes.mes - 1]}
              valor={moeda(mes.guardado_no_mes)}
              negativo={Number(mes.guardado_no_mes) < 0}
            />
          ))
        )}
      </div>

      <div className="mt-3 border-t-2 border-roxo-100 pt-3 dark:border-roxo-600">
        <Linha
          rotulo="Total guardado"
          valor={moeda(resumo.total_guardado)}
          destaque
        />

        {/* Onde a reserva está: a caixinha e o investimento são lugares
            diferentes, e o total sozinho esconderia isso. */}
        {reservas.length > 1 && (
          <ul className="mt-2 space-y-1">
            {reservas.map((conta) => (
              <li
                key={conta.conta_id}
                className="flex items-center justify-between text-xs"
              >
                <span className="flex items-center gap-1.5 text-roxo-400 dark:text-roxo-200">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: conta.cor }}
                  />
                  {conta.nome}
                </span>
                <span className="tabular-nums text-roxo-500 dark:text-roxo-100">
                  {moeda(conta.guardado)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
