import { Moldura } from './Moldura';
import { moeda } from '../../lib/formato';
import type { Conta, Fatura, GastoFixo } from '../../types/api';

/**
 * O que vence hoje: gastos fixos e faturas de cartão. Calculado no cliente
 * a partir do que a página já buscou — sem endpoint novo (mesmo princípio
 * de "despesas diárias reais").
 */
export function LembreteDia({
  gastosFixos,
  cartoes,
  faturas,
  ano,
  mes,
}: {
  gastosFixos: GastoFixo[];
  cartoes: Conta[];
  faturas: Record<number, Fatura>;
  ano: number;
  mes: number;
}) {
  const hoje = new Date();
  const ehMesCorrente =
    hoje.getFullYear() === ano && hoje.getMonth() + 1 === mes;
  const dia = hoje.getDate();

  const gastosHoje = ehMesCorrente
    ? gastosFixos.filter(
        (g) =>
          g.ativo &&
          g.dia_vencimento === dia &&
          !g.meses.some((m) => m.mes === mes && m.situacao === 'pago'),
      )
    : [];

  const cartoesHoje = ehMesCorrente
    ? cartoes.filter(
        (c) =>
          c.dia_vencimento_fatura === dia &&
          faturas[c.id]?.situacao !== 'pago',
      )
    : [];

  const total = gastosHoje.length + cartoesHoje.length;

  return (
    <Moldura titulo="Vence hoje">
      {!ehMesCorrente ? (
        <p className="text-white/40">Este não é o mês corrente.</p>
      ) : total === 0 ? (
        <p className="text-white/40">Nada vencendo hoje.</p>
      ) : (
        <ul className="space-y-1.5">
          {gastosHoje.map((g) => (
            <li key={`g${g.id}`} className="flex items-center justify-between">
              <span className="truncate text-white/80">{g.descricao}</span>
              <span className="ml-2 shrink-0 tabular-nums text-white/60">
                {moeda(g.valor)}
              </span>
            </li>
          ))}
          {cartoesHoje.map((c) => {
            const valor = faturas[c.id]?.valor_em_aberto ?? '0';
            return (
              <li key={`c${c.id}`} className="flex items-center justify-between">
                <span className="truncate text-white/80">💳 {c.nome}</span>
                <span className="ml-2 shrink-0 tabular-nums text-white/60">
                  {moeda(valor)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Moldura>
  );
}
