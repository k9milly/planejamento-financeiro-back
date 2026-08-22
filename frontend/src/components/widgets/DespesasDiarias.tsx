import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import { Card, Linha } from '../Card';
import { moeda } from '../../lib/formato';
import type { Lancamento } from '../../types/api';

/**
 * Quanto saiu por dia no mês, e a média diária.
 *
 * Calculado no cliente a partir dos lançamentos que a tela já tem — não há
 * endpoint para isto, e nem precisa (ver "O que este contrato não cobre" em
 * `docs/CONTRATO-API.md`).
 *
 * A média divide pelos dias **já decorridos**, não pelos 30 do mês: no dia 5,
 * dividir por 30 daria uma média artificialmente baixa e passaria a impressão
 * errada de que o mês está sob controle.
 */
export function DespesasDiarias({
  lancamentos,
  ano,
  mes,
}: {
  lancamentos: Lancamento[];
  ano: number;
  mes: number;
}) {
  const ultimoDia = new Date(ano, mes, 0).getDate();

  const porDia = new Array<number>(ultimoDia).fill(0);
  for (const lanc of lancamentos) {
    if (lanc.tipo !== 'saida') continue;
    const dia = Number(lanc.data.split('-')[2]);
    if (dia >= 1 && dia <= ultimoDia) porDia[dia - 1] += Number(lanc.valor);
  }

  const total = porDia.reduce((s, v) => s + v, 0);

  const hoje = new Date();
  const mesCorrente =
    hoje.getFullYear() === ano && hoje.getMonth() + 1 === mes;
  const diasDecorridos = mesCorrente ? hoje.getDate() : ultimoDia;

  const dados = porDia.map((valor, indice) => ({ dia: indice + 1, valor }));
  const maiorDia = porDia.indexOf(Math.max(...porDia)) + 1;

  return (
    <Card titulo="Despesas diárias" preencher>
      {total === 0 ? (
        <p className="text-sm text-roxo-300">Nenhuma saída registrada.</p>
      ) : (
        <div className="flex h-full min-h-0 flex-col">
          <div className="shrink-0">
            <Linha
              rotulo={`Média por dia (${diasDecorridos} ${diasDecorridos === 1 ? 'dia' : 'dias'})`}
              valor={moeda(total / diasDecorridos)}
              destaque
            />
            <p className="text-xs text-roxo-300">
              Maior gasto no dia {maiorDia}: {moeda(porDia[maiorDia - 1])}
            </p>
          </div>

          <div className="mt-3 min-h-0 flex-1">
            <ResponsiveContainer width="100%" height="100%" minHeight={90}>
              <BarChart data={dados} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                <XAxis
                  dataKey="dia"
                  tick={{ fontSize: 9 }}
                  interval={4}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(141, 119, 153, 0.15)' }}
                  formatter={(valor: unknown) => moeda(Number(valor ?? 0))}
                  labelFormatter={(dia) => `Dia ${dia}`}
                  contentStyle={{
                    borderRadius: '0.5rem',
                    border: 'none',
                    fontSize: '0.75rem',
                    backgroundColor: '#2b2440',
                    color: '#f5f4f7',
                  }}
                />
                <Bar dataKey="valor" fill="#8d7799" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Card>
  );
}
