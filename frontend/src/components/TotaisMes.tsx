import { Card, Linha } from './Card';
import { moeda, NOMES_MESES } from '../lib/formato';
import type { ResumoMes } from '../types/api';

/** Container "Total de {mês}": entradas, saídas, guardado e saldo. */
export function TotaisMes({
  mes,
  preencher,
}: {
  mes: ResumoMes;
  /** No modo painel, quem define a altura é a célula da grade. */
  preencher?: boolean;
}) {
  const rendimentos = Number(mes.rendimentos);
  const perdas = Number(mes.perdas);
  const transferido = Number(mes.transferido);

  // `por_conta` já vem só com contas correntes — o backend manda cartão em
  // `por_cartao` (ADR-0002). O saldo acima, portanto, é o dinheiro que existe
  // de verdade. O aviso abaixo só aparece quando há dívida a explicar.
  const emAberto = mes.por_cartao.reduce((s, c) => s + Number(c.saldo), 0);

  return (
    <Card titulo={`Total de ${NOMES_MESES[mes.mes - 1]}`} preencher={preencher}>
      <Linha rotulo="Entradas" valor={moeda(mes.entradas)} />
      <Linha rotulo="Saídas" valor={moeda(mes.saidas)} />
      <Linha
        rotulo="Total guardado"
        valor={moeda(mes.guardado_no_mes)}
        negativo={Number(mes.guardado_no_mes) < 0}
      />
      {rendimentos !== 0 && (
        <Linha rotulo="Rendimentos" valor={moeda(rendimentos)} />
      )}
      {perdas !== 0 && (
        <Linha rotulo="Perdas" valor={moeda(perdas)} negativo />
      )}

      <div className="mt-3 border-t-2 border-roxo-100 pt-3 dark:border-roxo-600">
        <Linha
          rotulo="Saldo"
          valor={moeda(mes.saldo)}
          destaque
          negativo={Number(mes.saldo) < 0}
        />

        {/* Saldo de cada conta, para responder "dá para pagar isso por aqui?". */}
        {mes.por_conta.length > 1 && (
          <ul className="mt-2 space-y-1">
            {mes.por_conta.map((conta) => (
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
                <span
                  className={`tabular-nums ${
                    Number(conta.saldo) < 0
                      ? 'text-rose-600 dark:text-rose-400'
                      : 'text-roxo-500 dark:text-roxo-100'
                  }`}
                >
                  {moeda(conta.saldo)}
                </span>
              </li>
            ))}
          </ul>
        )}

        <p className="mt-2 text-xs text-roxo-300">
          Abertura do mês: {moeda(mes.saldo_inicial)}
          {/* Transferência não muda o patrimônio; aparece só para conferência
              contra o extrato do banco. */}
          {transferido !== 0 && ` · ${moeda(transferido)} entre contas`}
        </p>

        {emAberto < 0 && (
          <p className="mt-2 rounded-lg bg-roxo-50 px-3 py-2 text-xs leading-relaxed text-roxo-400 dark:bg-roxo-950 dark:text-roxo-200">
            Não inclui {moeda(-emAberto)} de fatura em aberto no cartão: uma
            compra no crédito só sai do saldo quando a fatura é paga.
          </p>
        )}
      </div>
    </Card>
  );
}
