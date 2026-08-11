import { Card } from './Card';
import { diaMes, ESTILO_TIPO, moeda } from '../lib/formato';
import type { Lancamento } from '../types/api';

interface Props {
  titulo: string;
  lancamentos: Lancamento[];
  somenteLeitura: boolean;
  aoExcluir: (id: number) => void;
}

/** Container principal do mês: todas as entradas e saídas da conta. */
export function TabelaLancamentos({
  titulo,
  lancamentos,
  somenteLeitura,
  aoExcluir,
}: Props) {
  return (
    <Card titulo={titulo} largo>
      {lancamentos.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">
          Nenhum lançamento neste mês.
        </p>
      ) : (
        // A tabela rola sozinha em telas estreitas; a página nunca rola na horizontal.
        <div className="-mx-5 overflow-x-auto px-5">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="pb-2 font-medium">Data</th>
                <th className="pb-2 font-medium">Tipo</th>
                <th className="pb-2 font-medium">Categoria</th>
                <th className="pb-2 font-medium">Descrição</th>
                <th className="pb-2 text-right font-medium">Valor</th>
                {!somenteLeitura && <th className="pb-2" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {lancamentos.map((lanc) => {
                const estilo = ESTILO_TIPO[lanc.tipo];
                return (
                  <tr key={lanc.id} className="hover:bg-slate-50">
                    <td className="py-2 tabular-nums text-slate-500">
                      {diaMes(lanc.data)}
                    </td>
                    <td className="py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${estilo.classe}`}
                      >
                        {estilo.rotulo}
                        {lanc.destino && ` (${lanc.destino})`}
                      </span>
                    </td>
                    <td className="py-2 text-slate-600">
                      {lanc.categoria?.nome ?? '—'}
                    </td>
                    <td className="max-w-xs truncate py-2 text-slate-600">
                      {lanc.descricao || '—'}
                    </td>
                    <td className="py-2 text-right tabular-nums font-medium text-slate-900">
                      {moeda(lanc.valor)}
                    </td>
                    {!somenteLeitura && (
                      <td className="py-2 text-right">
                        <button
                          onClick={() => aoExcluir(lanc.id)}
                          className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                          aria-label={`Excluir lançamento de ${moeda(lanc.valor)}`}
                        >
                          Excluir
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
