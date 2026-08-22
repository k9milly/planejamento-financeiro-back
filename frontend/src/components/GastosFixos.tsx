import { useEffect, useState, type FormEvent } from 'react';
import { Card } from './Card';
import { ESTILO_FORMA_PAGAMENTO, moeda } from '../lib/formato';
import type { Conta, FormaPagamento, GastoFixo } from '../types/api';

interface Props {
  gastos: GastoFixo[];
  contas: Conta[];
  mes: number;
  somenteLeitura: boolean;
  aoCriar: (dados: {
    descricao: string;
    valor: string;
    dia_vencimento: number;
    conta_id: number;
    forma_pagamento?: FormaPagamento | null;
  }) => Promise<void>;
  aoAtualizar: (
    id: number,
    dados: Partial<{
      descricao: string;
      valor: string;
      dia_vencimento: number;
      conta_id: number;
      forma_pagamento: FormaPagamento | null;
    }>,
  ) => Promise<void>;
  aoAlternar: (gasto: GastoFixo, pago: boolean) => Promise<void>;
  aoExcluir: (id: number) => Promise<void>;
}

const FORMAS_PAGAMENTO = Object.keys(ESTILO_FORMA_PAGAMENTO) as FormaPagamento[];

/**
 * Container de gastos fixos do mês selecionado.
 *
 * Marcar como pago gera o lançamento de saída correspondente; desmarcar o
 * remove. O total mostrado separa o que já saiu da conta do que ainda falta.
 */
export function GastosFixos({
  gastos,
  contas,
  mes,
  somenteLeitura,
  aoCriar,
  aoAtualizar,
  aoAlternar,
  aoExcluir,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [descricao, setDescricao] = useState('');
  const [valor, setValor] = useState('');
  const [dia, setDia] = useState('');
  const [contaId, setContaId] = useState('');
  const [formaPagamento, setFormaPagamento] = useState<FormaPagamento>('debito');
  const [erro, setErro] = useState('');

  const ehCredito = formaPagamento === 'credito';
  const contasCompativeis = contas.filter((c) =>
    ehCredito ? c.tipo === 'cartao_credito' : c.tipo === 'corrente',
  );

  // Seleciona a primeira conta compatível assim que a lista chega, e troca de
  // novo se deixar de ser compatível (ex.: mudou pra crédito).
  useEffect(() => {
    if (contasCompativeis.some((c) => String(c.id) === contaId)) return;
    setContaId(contasCompativeis.length ? String(contasCompativeis[0].id) : '');
  }, [contasCompativeis, contaId]);

  const ativos = gastos.filter((g) => g.ativo);
  const estaPago = (gasto: GastoFixo) =>
    gasto.meses.some((m) => m.mes === mes && m.situacao === 'pago');

  const pagos = ativos.filter(estaPago);
  const total = (lista: GastoFixo[]) =>
    lista.reduce((soma, g) => soma + Number(g.valor), 0);
  const pendente = total(ativos) - total(pagos);

  function iniciarEdicao(gasto: GastoFixo) {
    setEditandoId(gasto.id);
    setDescricao(gasto.descricao);
    setValor(gasto.valor);
    setDia(String(gasto.dia_vencimento));
    setContaId(String(gasto.conta_id));
    setFormaPagamento(gasto.forma_pagamento ?? 'debito');
    setAberto(true);
  }

  function fecharFormulario() {
    setAberto(false);
    setEditandoId(null);
    setDescricao('');
    setValor('');
    setDia('');
  }

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');
    // Categoria não é editável aqui de propósito: um gasto fixo que muda de
    // categoria deixou de ser fixo, então some desta lista — não faz sentido
    // essa tela mexer nela.
    const dados = {
      descricao,
      valor,
      dia_vencimento: Number(dia),
      conta_id: Number(contaId),
      forma_pagamento: formaPagamento,
    };
    try {
      if (editandoId !== null) {
        await aoAtualizar(editandoId, dados);
      } else {
        await aoCriar(dados);
      }
      fecharFormulario();
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar.');
    }
  }

  const campo =
    'rounded-lg border border-roxo-100 dark:border-roxo-700 px-3 py-2 text-sm focus:border-roxo-400 dark:focus:border-roxo-300 focus:outline-none';

  return (
    <Card
      titulo="Gastos fixos"
      acao={
        !somenteLeitura && (
          <button
            type="button"
            onClick={() => (aberto ? fecharFormulario() : setAberto(true))}
            className="text-xs font-medium text-roxo-400 dark:text-roxo-200 hover:text-roxo-600 dark:hover:text-roxo-50"
          >
            {aberto ? 'Cancelar' : '+ Novo'}
          </button>
        )
      }
    >
      {aberto && (
        <form onSubmit={enviar} className="mb-4 space-y-2">
          <input
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            placeholder="Descrição (ex.: Internet)"
            className={`${campo} w-full`}
            required
          />
          <div className="flex flex-wrap gap-2">
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              placeholder="Valor"
              className={`${campo} w-28`}
              required
            />
            <input
              type="number"
              min="1"
              max="31"
              value={dia}
              onChange={(e) => setDia(e.target.value)}
              placeholder="Dia"
              className={`${campo} w-20`}
              aria-label="Dia do vencimento"
              required
            />
            <select
              value={formaPagamento}
              onChange={(e) => setFormaPagamento(e.target.value as FormaPagamento)}
              className={`${campo} flex-1`}
              aria-label="Forma de pagamento"
            >
              {FORMAS_PAGAMENTO.map((f) => (
                <option key={f} value={f}>
                  {ESTILO_FORMA_PAGAMENTO[f].rotulo}
                </option>
              ))}
            </select>
            <select
              value={contaId}
              onChange={(e) => setContaId(e.target.value)}
              className={`${campo} flex-1`}
              aria-label="Conta"
              required
            >
              {contasCompativeis.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="w-full rounded-lg bg-roxo-500 dark:bg-roxo-400 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400"
          >
            {editandoId !== null ? 'Salvar' : 'Adicionar'}
          </button>
          {erro && <p className="text-sm text-rose-600">{erro}</p>}
        </form>
      )}

      {ativos.length === 0 ? (
        <p className="text-sm text-roxo-300">Nenhum gasto fixo cadastrado.</p>
      ) : (
        <ul className="divide-y divide-roxo-100 dark:divide-roxo-700">
          {ativos.map((gasto) => {
            const pago = estaPago(gasto);
            return (
              <li key={gasto.id} className="group flex items-center gap-3 py-2">
                <input
                  type="checkbox"
                  checked={pago}
                  disabled={somenteLeitura}
                  onChange={() => void aoAlternar(gasto, !pago)}
                  className="h-4 w-4 rounded border-roxo-200 dark:border-roxo-600"
                  aria-label={`${gasto.descricao} pago`}
                />
                <div className="min-w-0 flex-1">
                  <p
                    className={`truncate text-sm ${
                      pago ? 'text-roxo-300 line-through' : 'text-roxo-600 dark:text-roxo-100'
                    }`}
                  >
                    {gasto.descricao}
                  </p>
                  <p className="text-xs text-roxo-300">
                    vence dia {gasto.dia_vencimento}
                    {contas.length > 1 &&
                      ` · ${
                        contas.find((c) => c.id === gasto.conta_id)?.nome ?? ''
                      }`}
                  </p>
                </div>
                <span className="tabular-nums text-sm font-medium text-roxo-700 dark:text-roxo-50">
                  {moeda(gasto.valor)}
                </span>
                {!somenteLeitura && (
                  <span className="flex items-center gap-2 opacity-0 group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => iniciarEdicao(gasto)}
                      className="text-xs text-roxo-300 hover:text-roxo-500"
                      aria-label={`Editar ${gasto.descricao}`}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      onClick={() => void aoExcluir(gasto.id)}
                      className="text-xs text-roxo-200 hover:text-rose-600"
                      aria-label={`Excluir ${gasto.descricao}`}
                    >
                      ✕
                    </button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {ativos.length > 0 && (
        <div className="mt-3 flex justify-between border-t-2 border-roxo-100 dark:border-roxo-700 pt-3 text-sm">
          <span className="text-roxo-500 dark:text-roxo-200">
            Falta pagar
            <span className="ml-1 text-xs text-roxo-300">
              ({ativos.length - pagos.length} de {ativos.length})
            </span>
          </span>
          <span className="tabular-nums font-semibold text-roxo-700 dark:text-roxo-50">
            {moeda(pendente)}
          </span>
        </div>
      )}
    </Card>
  );
}
