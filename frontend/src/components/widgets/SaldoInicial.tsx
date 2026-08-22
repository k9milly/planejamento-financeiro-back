import { Card, Linha } from '../Card';
import { moeda, NOMES_MESES } from '../../lib/formato';
import type { ResumoMes } from '../../types/api';

/**
 * Com quanto o mês começou, e o que ele fez com isso.
 *
 * A pergunta que este bloco responde é "o mês está me deixando melhor ou pior
 * do que me encontrou" — por isso a variação, e não só a abertura.
 */
export function SaldoInicial({ mes }: { mes: ResumoMes }) {
  const abertura = Number(mes.saldo_inicial);
  const fechamento = Number(mes.saldo);
  const variacao = fechamento - abertura;

  return (
    <Card titulo={`Abertura de ${NOMES_MESES[mes.mes - 1].toLowerCase()}`} preencher>
      <Linha rotulo="Saldo inicial" valor={moeda(abertura)} negativo={abertura < 0} />
      <Linha rotulo="Saldo atual" valor={moeda(fechamento)} negativo={fechamento < 0} />

      <div className="mt-3 border-t-2 border-roxo-100 pt-3 dark:border-roxo-600">
        <Linha
          rotulo={variacao >= 0 ? 'Sobrou no mês' : 'Consumiu do saldo'}
          valor={moeda(Math.abs(variacao))}
          destaque
          negativo={variacao < 0}
        />
      </div>
    </Card>
  );
}
