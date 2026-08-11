import { Card, Linha } from './Card';
import { moeda, NOMES_MESES } from '../lib/formato';
import type { ResumoAno } from '../types/api';

/**
 * Container "Total guardado": quanto foi guardado em cada mês, mais o total.
 *
 * Meses sem movimentação na reserva são omitidos — listar doze linhas zeradas
 * esconderia as que importam.
 */
export function TotalGuardado({ resumo }: { resumo: ResumoAno }) {
  const comMovimento = resumo.meses.filter(
    (m) => Number(m.guardado_no_mes) !== 0,
  );

  return (
    <Card titulo="Total guardado">
      <div className="divide-y divide-slate-100">
        {comMovimento.length === 0 ? (
          <p className="py-2 text-sm text-slate-400">
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

      <div className="mt-3 border-t-2 border-slate-200 pt-3">
        <Linha
          rotulo="Total guardado"
          valor={moeda(resumo.total_guardado)}
          destaque
        />
      </div>
    </Card>
  );
}
