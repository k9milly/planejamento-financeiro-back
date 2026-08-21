import { Card } from './Card';
import { diaMes, ESTILO_FORMA_PAGAMENTO, ESTILO_TIPO, moeda } from '../lib/formato';
import type { Conta, Lancamento } from '../types/api';

/** `forma_pagamento` nulo é tratado como débito em todo lugar (ADR-0001). */
function formaPagamento(lanc: Lancamento) {
  return ESTILO_FORMA_PAGAMENTO[lanc.forma_pagamento ?? 'debito'];
}

interface Props {
  titulo: string;
  lancamentos: Lancamento[];
  contas: Conta[];
  somenteLeitura: boolean;
  aoExcluir: (id: number) => void;
}

/**
 * Container principal do mês: todas as movimentações.
 *
 * Em telas largas é uma tabela; em telas estreitas vira uma lista de cartões.
 * Uma tabela de seis colunas num celular só rolaria para os lados, e o uso
 * principal deste app é justamente conferir as contas pelo telefone.
 */
export function TabelaLancamentos({
  titulo,
  lancamentos,
  contas,
  somenteLeitura,
  aoExcluir,
}: Props) {
  const nomeConta = (id: number | null) =>
    contas.find((c) => c.id === id)?.nome ?? '—';

  return (
    <Card titulo={titulo} largo>
      {lancamentos.length === 0 ? (
        <p className="py-6 text-center text-sm text-roxo-300">
          Nenhum lançamento neste mês.
        </p>
      ) : (
        <>
          {/* Celular: cartões empilhados. */}
          <ul className="divide-y divide-roxo-100 md:hidden dark:divide-roxo-700">
            {lancamentos.map((lanc) => {
              const estilo = ESTILO_TIPO[lanc.tipo];
              return (
                <li key={lanc.id} className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-roxo-700 dark:text-roxo-50">
                        {lanc.descricao || estilo.rotulo}
                      </p>
                      <p className="mt-0.5 text-xs text-roxo-400 dark:text-roxo-200">
                        {diaMes(lanc.data)} · {nomeConta(lanc.conta_id)}
                        {lanc.conta_destino_id !== null &&
                          ` → ${nomeConta(lanc.conta_destino_id)}`}
                        {lanc.categoria && ` · ${lanc.categoria.nome}`}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="tabular-nums text-sm font-semibold text-roxo-700 dark:text-roxo-50">
                        {moeda(lanc.valor)}
                      </p>
                      <span
                        className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${estilo.classe}`}
                      >
                        {estilo.rotulo}
                      </span>
                      {lanc.tipo === 'saida' && (
                        <span
                          className="mt-1 block text-[10px] text-roxo-400 dark:text-roxo-200"
                          title={formaPagamento(lanc).rotulo}
                        >
                          {formaPagamento(lanc).icone} {formaPagamento(lanc).rotulo}
                        </span>
                      )}
                    </div>
                  </div>
                  {!somenteLeitura && (
                    <button
                      onClick={() => aoExcluir(lanc.id)}
                      className="mt-1 text-xs text-roxo-300 hover:text-rose-600"
                    >
                      Excluir
                    </button>
                  )}
                </li>
              );
            })}
          </ul>

          {/* Tela larga: tabela. */}
          <div className="-mx-5 hidden overflow-x-auto px-5 md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-roxo-100 text-left text-xs uppercase tracking-wide text-roxo-300 dark:border-roxo-700">
                  <th className="pb-2 font-medium">Data</th>
                  <th className="pb-2 font-medium">Tipo</th>
                  <th className="pb-2 font-medium">Conta</th>
                  <th className="pb-2 font-medium">Categoria</th>
                  <th className="pb-2 font-medium">Pagamento</th>
                  <th className="pb-2 font-medium">Descrição</th>
                  <th className="pb-2 text-right font-medium">Valor</th>
                  {!somenteLeitura && <th className="pb-2" />}
                </tr>
              </thead>
              <tbody className="divide-y divide-roxo-100 dark:divide-roxo-700">
                {lancamentos.map((lanc) => {
                  const estilo = ESTILO_TIPO[lanc.tipo];
                  return (
                    <tr
                      key={lanc.id}
                      className="hover:bg-roxo-50 dark:hover:bg-roxo-800"
                    >
                      <td className="py-2 tabular-nums text-roxo-400 dark:text-roxo-200">
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
                      <td className="py-2 text-roxo-500 dark:text-roxo-200">
                        {nomeConta(lanc.conta_id)}
                        {lanc.conta_destino_id !== null && (
                          <span className="text-roxo-300">
                            {' → '}
                            {nomeConta(lanc.conta_destino_id)}
                          </span>
                        )}
                      </td>
                      <td className="py-2 text-roxo-500 dark:text-roxo-200">
                        {lanc.categoria?.nome ?? '—'}
                      </td>
                      <td className="py-2 text-roxo-500 dark:text-roxo-200">
                        {lanc.tipo === 'saida' ? (
                          <span title={formaPagamento(lanc).rotulo}>
                            {formaPagamento(lanc).icone}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="max-w-xs truncate py-2 text-roxo-500 dark:text-roxo-200">
                        {lanc.descricao || '—'}
                      </td>
                      <td className="py-2 text-right tabular-nums font-medium text-roxo-700 dark:text-roxo-50">
                        {moeda(lanc.valor)}
                      </td>
                      {!somenteLeitura && (
                        <td className="py-2 text-right">
                          <button
                            onClick={() => aoExcluir(lanc.id)}
                            className="rounded px-2 py-1 text-xs text-roxo-300 hover:bg-rose-50 hover:text-rose-600"
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
        </>
      )}
    </Card>
  );
}
