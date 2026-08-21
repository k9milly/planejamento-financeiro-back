import { Card } from './Card';
import { moeda, NOMES_MESES } from '../lib/formato';
import type { Conta, Fatura, GastoFixo } from '../types/api';

interface Props {
  gastos: GastoFixo[];
  /** Cartões ativos; cada um plota um lembrete no dia de vencimento da fatura. */
  cartoes: Conta[];
  /** Fatura do mês selecionado, por cartão. */
  faturas: Record<number, Fatura>;
  ano: number;
  mes: number;
  somenteLeitura: boolean;
  aoAlternar: (gasto: GastoFixo, pago: boolean) => Promise<void>;
  aoAlternarFatura: (cartao: Conta, pago: boolean) => Promise<void>;
}

const DIAS_SEMANA = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];

/** Um vencimento no calendário: de gasto fixo, ou de fatura de cartão. */
type Vencimento =
  | { origem: 'gasto'; gasto: GastoFixo }
  | { origem: 'fatura'; cartao: Conta };

/**
 * Calendário do mês marcando o dia de vencimento de cada gasto fixo e de cada
 * fatura de cartão.
 *
 * Um dia pode ter mais de um vencimento, então cada célula lista todos. Clicar
 * em um vencimento alterna pago/pendente, igual à lista — as duas visões
 * operam sobre o mesmo dado.
 */
export function CalendarioVencimentos({
  gastos,
  cartoes,
  faturas,
  ano,
  mes,
  somenteLeitura,
  aoAlternar,
  aoAlternarFatura,
}: Props) {
  const ultimoDia = new Date(ano, mes, 0).getDate();
  // getDay() devolve 0 para domingo, que é como a grade começa.
  const deslocamento = new Date(ano, mes - 1, 1).getDay();

  const ativos = gastos.filter((g) => g.ativo);
  const estaPago = (gasto: GastoFixo) =>
    gasto.meses.some((m) => m.mes === mes && m.situacao === 'pago');
  const faturaPaga = (cartao: Conta) => faturas[cartao.id]?.situacao === 'pago';

  /** Vencimentos por dia. Dia 31 em mês de 30 cai no último dia, como no backend. */
  const porDia = new Map<number, Vencimento[]>();
  for (const gasto of ativos) {
    const dia = Math.min(gasto.dia_vencimento, ultimoDia);
    porDia.set(dia, [...(porDia.get(dia) ?? []), { origem: 'gasto', gasto }]);
  }
  for (const cartao of cartoes) {
    if (!cartao.dia_vencimento_fatura) continue;
    const dia = Math.min(cartao.dia_vencimento_fatura, ultimoDia);
    porDia.set(dia, [...(porDia.get(dia) ?? []), { origem: 'fatura', cartao }]);
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
    <Card titulo={`O que vence em ${NOMES_MESES[mes - 1].toLowerCase()}`}>
      {ativos.length === 0 && cartoes.length === 0 ? (
        <p className="text-sm text-roxo-300 dark:text-roxo-300">
          Cadastre um gasto fixo ou um cartão para ver os vencimentos aqui.
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
                vencimentos.length > 0 &&
                vencimentos.every((v) =>
                  v.origem === 'gasto' ? estaPago(v.gasto) : faturaPaga(v.cartao),
                );

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

                  {vencimentos.map((v) => {
                    if (v.origem === 'gasto') {
                      const { gasto } = v;
                      const pago = estaPago(gasto);
                      return (
                        <button
                          key={`gasto-${gasto.id}`}
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
                    }

                    const { cartao } = v;
                    const pago = faturaPaga(cartao);
                    const fatura = faturas[cartao.id];
                    return (
                      <button
                        key={`fatura-${cartao.id}`}
                        disabled={somenteLeitura}
                        onClick={() => void aoAlternarFatura(cartao, !pago)}
                        title={`Fatura ${cartao.nome}${
                          fatura ? ` — ${moeda(fatura.valor_em_aberto)}` : ''
                        }${pago ? ' (paga)' : ''}`}
                        // Cor e ícone próprios (💳), diferentes do gasto fixo.
                        className={`mt-0.5 block w-full truncate rounded px-1 py-0.5 text-[9px] leading-tight ${
                          pago
                            ? 'bg-emerald-100 text-emerald-700 line-through dark:bg-emerald-900 dark:text-emerald-200'
                            : 'bg-sky-200 text-sky-800 dark:bg-sky-700 dark:text-sky-50'
                        } ${somenteLeitura ? '' : 'hover:opacity-80'}`}
                      >
                        💳 {cartao.nome}
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
              gasto fixo
            </span>
            {cartoes.length > 0 && (
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-sm bg-sky-200 dark:bg-sky-700" />
                fatura do cartão
              </span>
            )}
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
