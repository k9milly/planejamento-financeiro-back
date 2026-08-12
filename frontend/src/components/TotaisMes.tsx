import { Card, Linha } from './Card';
import { moeda, NOMES_MESES } from '../lib/formato';
import type { ResumoMes } from '../types/api';

/** Container "Total de {mês}": entradas, saídas, guardado e saldo. */
export function TotaisMes({ mes }: { mes: ResumoMes }) {
  const rendimentos = Number(mes.rendimentos);
  const perdas = Number(mes.perdas);
  const transferido = Number(mes.transferido);

  return (
    <Card titulo={`Total de ${NOMES_MESES[mes.mes - 1]}`}>
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
      </div>
    </Card>
  );
}
