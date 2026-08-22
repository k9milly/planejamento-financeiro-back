import { Card } from '../Card';
import { moeda } from '../../lib/formato';
import type { CarteirasConta, Conta, Fatura } from '../../types/api';

/**
 * Fatura em aberto de cada cartão, com o dia do vencimento.
 *
 * O valor vem de `por_cartao`, onde `saldo` é a dívida (≤ 0) — a leitura da
 * interface é `-saldo`, como manda o contrato. Um saldo positivo significa
 * crédito a favor (pagou mais que devia), e é mostrado como tal em vez de
 * virar uma "fatura negativa" sem sentido.
 */
export function FaturaCartao({
  contas,
  posicaoCartoes,
  faturas,
}: {
  contas: Conta[];
  posicaoCartoes: CarteirasConta[];
  faturas: Record<number, Fatura>;
}) {
  const cartoes = contas.filter((c) => c.tipo === 'cartao_credito');

  return (
    <Card titulo="Fatura do cartão" preencher>
      {cartoes.length === 0 ? (
        <p className="text-sm text-roxo-300">Nenhum cartão de crédito cadastrado.</p>
      ) : (
        <ul className="space-y-3">
          {cartoes.map((cartao) => {
            const saldo = Number(
              posicaoCartoes.find((p) => p.conta_id === cartao.id)?.saldo ?? '0',
            );
            const fatura = faturas[cartao.id];
            const paga = fatura?.situacao === 'pago';
            const aFavor = saldo > 0;

            return (
              <li key={cartao.id}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="flex items-center gap-1.5 text-sm text-roxo-600 dark:text-roxo-100">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: cartao.cor }}
                    />
                    {cartao.nome}
                  </span>
                  <span
                    className={`tabular-nums text-lg font-semibold ${
                      paga || saldo === 0
                        ? 'text-roxo-400 dark:text-roxo-200'
                        : aFavor
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-rose-600 dark:text-rose-400'
                    }`}
                  >
                    {moeda(Math.abs(saldo))}
                  </span>
                </div>

                <p className="text-xs text-roxo-300">
                  {aFavor
                    ? 'crédito a favor'
                    : paga
                      ? 'fatura paga'
                      : saldo === 0
                        ? 'nada lançado neste mês'
                        : 'em aberto'}
                  {cartao.dia_vencimento_fatura
                    ? ` · vence dia ${cartao.dia_vencimento_fatura}`
                    : ''}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
