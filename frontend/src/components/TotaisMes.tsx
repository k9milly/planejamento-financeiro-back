import { Card, Linha } from './Card';
import { moeda, NOMES_MESES } from '../lib/formato';
import type { ResumoMes } from '../types/api';

/** Container "Total de {mês}": entradas, saídas, guardado e saldo. */
export function TotaisMes({ mes }: { mes: ResumoMes }) {
  const rendimento =
    Number(mes.rendimento_conta) + Number(mes.rendimento_guardado);

  return (
    <Card titulo={`Total de ${NOMES_MESES[mes.mes - 1]}`}>
      <Linha rotulo="Entradas" valor={moeda(mes.entradas)} />
      <Linha rotulo="Saídas" valor={moeda(mes.saidas)} />
      <Linha
        rotulo="Total guardado"
        valor={moeda(mes.guardado_no_mes)}
        negativo={Number(mes.guardado_no_mes) < 0}
      />
      {rendimento !== 0 && (
        <Linha rotulo="Rendimentos" valor={moeda(rendimento)} />
      )}

      <div className="mt-3 border-t-2 border-slate-200 pt-3">
        <Linha
          rotulo="Saldo"
          valor={moeda(mes.saldo)}
          destaque
          negativo={Number(mes.saldo) < 0}
        />
        <p className="mt-1 text-xs text-slate-400">
          Abertura do mês: {moeda(mes.saldo_inicial)}
        </p>
      </div>
    </Card>
  );
}
