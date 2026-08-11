import { useState, type FormEvent } from 'react';
import { Card } from './Card';
import { moeda } from '../lib/formato';
import type { Categoria, GastoFixo } from '../types/api';

interface Props {
  gastos: GastoFixo[];
  categorias: Categoria[];
  mes: number;
  somenteLeitura: boolean;
  aoCriar: (dados: {
    descricao: string;
    valor: string;
    dia_vencimento: number;
    categoria_id?: number | null;
  }) => Promise<void>;
  aoAlternar: (gasto: GastoFixo, pago: boolean) => Promise<void>;
  aoExcluir: (id: number) => Promise<void>;
}

/**
 * Container de gastos fixos do mês selecionado.
 *
 * Marcar como pago gera o lançamento de saída correspondente; desmarcar o
 * remove. O total mostrado separa o que já saiu da conta do que ainda falta.
 */
export function GastosFixos({
  gastos,
  categorias,
  mes,
  somenteLeitura,
  aoCriar,
  aoAlternar,
  aoExcluir,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [descricao, setDescricao] = useState('');
  const [valor, setValor] = useState('');
  const [dia, setDia] = useState('1');
  const [categoriaId, setCategoriaId] = useState('');
  const [erro, setErro] = useState('');

  const ativos = gastos.filter((g) => g.ativo);
  const estaPago = (gasto: GastoFixo) =>
    gasto.meses.some((m) => m.mes === mes && m.situacao === 'pago');

  const pagos = ativos.filter(estaPago);
  const total = (lista: GastoFixo[]) =>
    lista.reduce((soma, g) => soma + Number(g.valor), 0);
  const pendente = total(ativos) - total(pagos);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');
    try {
      await aoCriar({
        descricao,
        valor,
        dia_vencimento: Number(dia),
        categoria_id: categoriaId ? Number(categoriaId) : null,
      });
      setDescricao('');
      setValor('');
      setAberto(false);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar.');
    }
  }

  const campo =
    'rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none';

  return (
    <Card
      titulo="Gastos fixos"
      acao={
        !somenteLeitura && (
          <button
            onClick={() => setAberto(!aberto)}
            className="text-xs font-medium text-slate-500 hover:text-slate-900"
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
              className={`${campo} w-20`}
              aria-label="Dia do vencimento"
              required
            />
            <select
              value={categoriaId}
              onChange={(e) => setCategoriaId(e.target.value)}
              className={`${campo} flex-1`}
              aria-label="Categoria"
            >
              <option value="">Sem categoria</option>
              {categorias.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            Adicionar
          </button>
          {erro && <p className="text-sm text-rose-600">{erro}</p>}
        </form>
      )}

      {ativos.length === 0 ? (
        <p className="text-sm text-slate-400">Nenhum gasto fixo cadastrado.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {ativos.map((gasto) => {
            const pago = estaPago(gasto);
            return (
              <li key={gasto.id} className="group flex items-center gap-3 py-2">
                <input
                  type="checkbox"
                  checked={pago}
                  disabled={somenteLeitura}
                  onChange={() => void aoAlternar(gasto, !pago)}
                  className="h-4 w-4 rounded border-slate-300"
                  aria-label={`${gasto.descricao} pago`}
                />
                <div className="min-w-0 flex-1">
                  <p
                    className={`truncate text-sm ${
                      pago ? 'text-slate-400 line-through' : 'text-slate-700'
                    }`}
                  >
                    {gasto.descricao}
                  </p>
                  <p className="text-xs text-slate-400">
                    vence dia {gasto.dia_vencimento}
                  </p>
                </div>
                <span className="tabular-nums text-sm font-medium text-slate-900">
                  {moeda(gasto.valor)}
                </span>
                {!somenteLeitura && (
                  <button
                    onClick={() => void aoExcluir(gasto.id)}
                    className="text-xs text-slate-300 opacity-0 hover:text-rose-600 group-hover:opacity-100"
                    aria-label={`Excluir ${gasto.descricao}`}
                  >
                    ✕
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {ativos.length > 0 && (
        <div className="mt-3 flex justify-between border-t-2 border-slate-200 pt-3 text-sm">
          <span className="text-slate-600">
            Falta pagar
            <span className="ml-1 text-xs text-slate-400">
              ({ativos.length - pagos.length} de {ativos.length})
            </span>
          </span>
          <span className="tabular-nums font-semibold text-slate-900">
            {moeda(pendente)}
          </span>
        </div>
      )}
    </Card>
  );
}
