import { Card } from './Card';
import { moeda, NOMES_MESES } from '../lib/formato';
import type { GastoFixo } from '../types/api';

interface Props {
  gastos: GastoFixo[];
  ano: number;
  mes: number;
  somenteLeitura: boolean;
  aoAlternar: (gasto: GastoFixo, pago: boolean) => Promise<void>;
}

const DIAS_SEMANA = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];

/**
 * Calendário do mês marcando o dia de vencimento de cada gasto fixo.
 *
 * Um dia pode ter mais de um vencimento, então cada célula lista todos. Clicar
 * em um vencimento alterna pago/pendente, igual à lista — as duas visões
 * operam sobre o mesmo dado.
 */
export function CalendarioVencimentos({
  gastos,
  ano,
  mes,
  somenteLeitura,
  aoAlternar,
}: Props) {
  const ultimoDia = new Date(ano, mes, 0).getDate();
  // getDay() devolve 0 para domingo, que é como a grade começa.
  const deslocamento = new Date(ano, mes - 1, 1).getDay();

  const ativos = gastos.filter((g) => g.ativo);
  const estaPago = (gasto: GastoFixo) =>
    gasto.meses.some((m) => m.mes === mes && m.situacao === 'pago');

  /** Vencimentos por dia. Dia 31 em mês de 30 cai no último dia, como no backend. */
  const porDia = new Map<number, GastoFixo[]>();
  for (const gasto of ativos) {
    const dia = Math.min(gasto.dia_vencimento, ultimoDia);
    porDia.set(dia, [...(porDia.get(dia) ?? []), gasto]);
  }

  const hoje = new Date();
  const diaDeHoje =
    hoje.getFullYear() === ano && hoje.getMonth() + 1 === mes
      ? hoje.getDate()
      : null;

  const celulas = [
    ...Array.from({ length: deslocamento }, () => null),
    ...Array.from({ length: ultimoDia }, (_, i) => i + 1),
  ];

  return (
    <Card titulo={`Vencimentos de ${NOMES_MESES[mes - 1].toLowerCase()}`}>
      {ativos.length === 0 ? (
        <p className="text-sm text-roxo-300 dark:text-roxo-300">
          Cadastre um gasto fixo para ver os vencimentos aqui.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-7 gap-1">
            {DIAS_SEMANA.map((dia, i) => (
              <div
                key={i}
                className="pb-1 text-center text-[10px] font-medium uppercase text-roxo-300"
              >
                {dia}
              </div>
            ))}

            {celulas.map((dia, indice) => {
              if (dia === null) return <div key={`vazio-${indice}`} />;

              const vencimentos = porDia.get(dia) ?? [];
              const todosPagos =
                vencimentos.length > 0 && vencimentos.every(estaPago);

              return (
                <div
                  key={dia}
                  className={`min-h-[3.25rem] rounded-lg border p-1 ${
                    vencimentos.length
                      ? 'border-roxo-200 bg-roxo-50 dark:border-roxo-600 dark:bg-roxo-800'
                      : 'border-transparent'
                  }`}
                >
                  <span
                    className={`block text-center text-[11px] ${
                      dia === diaDeHoje
                        ? 'font-bold text-roxo-500 dark:text-roxo-200'
                        : 'text-roxo-300'
                    }`}
                  >
                    {dia}
                  </span>

                  {vencimentos.map((gasto) => {
                    const pago = estaPago(gasto);
                    return (
                      <button
                        key={gasto.id}
                        disabled={somenteLeitura}
                        onClick={() => void aoAlternar(gasto, !pago)}
                        title={`${gasto.descricao} — ${moeda(gasto.valor)}${
                          pago ? ' (pago)' : ''
                        }`}
                        className={`mt-0.5 block w-full truncate rounded px-1 py-0.5 text-[9px] leading-tight ${
                          pago
                            ? 'bg-emerald-100 text-emerald-700 line-through dark:bg-emerald-900 dark:text-emerald-200'
                            : 'bg-roxo-200 text-roxo-700 dark:bg-roxo-600 dark:text-roxo-50'
                        } ${somenteLeitura ? '' : 'hover:opacity-80'}`}
                      >
                        {gasto.descricao}
                      </button>
                    );
                  })}

                  {todosPagos && (
                    <span className="sr-only">todos os vencimentos pagos</span>
                  )}
                </div>
              );
            })}
          </div>

          <p className="mt-3 flex items-center gap-3 text-[10px] text-roxo-300">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm bg-roxo-200 dark:bg-roxo-600" />
              pendente
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm bg-emerald-100 dark:bg-emerald-900" />
              pago
            </span>
            <span>· clique para alternar</span>
          </p>
        </>
      )}
    </Card>
  );
}
