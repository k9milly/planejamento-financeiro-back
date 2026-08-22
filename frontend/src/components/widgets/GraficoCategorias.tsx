import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { Card } from '../Card';
import { moeda } from '../../lib/formato';
import type { Categoria, ResumoMes } from '../../types/api';

/** Usada quando a categoria não tem cor própria cadastrada. */
const CORES_RESERVA = ['#8d7799', '#a78bfa', '#f472b6', '#fbbf24', '#34d399', '#60a5fa'];

/**
 * Gastos por categoria em rosca.
 *
 * Complementa (não substitui) a versão em barras: a rosca responde "que fatia
 * do mês cada categoria levou", enquanto a tabela responde "quanto foi, em
 * reais, em cada uma". As duas existem no catálogo porque servem a perguntas
 * diferentes — e a usuária escolhe qual quer na tela.
 */
export function GraficoCategorias({
  mes,
  categorias,
}: {
  mes: ResumoMes;
  categorias: Categoria[];
}) {
  const dados = mes.gastos_por_categoria.map((gasto, indice) => ({
    nome: gasto.categoria,
    valor: Number(gasto.total),
    cor:
      categorias.find((c) => c.nome === gasto.categoria)?.cor ??
      CORES_RESERVA[indice % CORES_RESERVA.length],
  }));

  return (
    <Card titulo="Gastos por categoria" preencher>
      {dados.length === 0 ? (
        <p className="text-sm text-roxo-300">Nenhuma saída registrada.</p>
      ) : (
        <ResponsiveContainer width="100%" height="100%" minHeight={180}>
          <PieChart>
            <Pie
              data={dados}
              dataKey="valor"
              nameKey="nome"
              innerRadius="55%"
              outerRadius="80%"
              paddingAngle={2}
              stroke="none"
            >
              {dados.map((fatia) => (
                <Cell key={fatia.nome} fill={fatia.cor} />
              ))}
            </Pie>
            <Tooltip
              formatter={(valor: unknown) => moeda(Number(valor ?? 0))}
              contentStyle={{
                borderRadius: '0.5rem',
                border: 'none',
                fontSize: '0.75rem',
                // O tooltip do Recharts não herda o tema; sem isto ele fica
                // branco no escuro e some contra o card.
                backgroundColor: '#2b2440',
                color: '#f5f4f7',
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: '0.7rem' }}
              iconType="circle"
              iconSize={8}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
