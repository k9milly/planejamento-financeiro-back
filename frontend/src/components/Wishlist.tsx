import { useState, type FormEvent } from 'react';
import { Card } from './Card';
import { moeda } from '../lib/formato';
import type { Desejo, Importancia } from '../types/api';

interface Props {
  desejos: Desejo[];
  totalGuardado: string;
  somenteLeitura: boolean;
  aoCriar: (dados: {
    desejo: string;
    valor: string;
    importancia: Importancia;
  }) => Promise<void>;
  aoAtualizar: (id: number, dados: Partial<Desejo>) => Promise<void>;
  aoExcluir: (id: number) => Promise<void>;
}

const ESTILO_IMPORTANCIA: Record<Importancia, string> = {
  alta: 'bg-rose-100 text-rose-700',
  media: 'bg-amber-100 text-amber-700',
  baixa: 'bg-slate-100 text-slate-600',
};

const ORDEM: Record<Importancia, number> = { alta: 0, media: 1, baixa: 2 };

/**
 * Lista de desejos, com soma dos itens marcados.
 *
 * A soma é comparada com a reserva atual para responder à pergunta que motiva
 * a lista: "dá para comprar tudo isso com o que tenho guardado?".
 */
export function Wishlist({
  desejos,
  totalGuardado,
  somenteLeitura,
  aoCriar,
  aoAtualizar,
  aoExcluir,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [desejo, setDesejo] = useState('');
  const [valor, setValor] = useState('');
  const [importancia, setImportancia] = useState<Importancia>('media');
  const [erro, setErro] = useState('');

  const pendentes = [...desejos]
    .filter((d) => !d.comprado)
    .sort((a, b) => ORDEM[a.importancia] - ORDEM[b.importancia]);

  const marcados = pendentes.filter((d) => d.somar);
  const totalMarcado = marcados.reduce((s, d) => s + Number(d.valor), 0);
  const cabeNaReserva = totalMarcado <= Number(totalGuardado);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');
    try {
      await aoCriar({ desejo, valor, importancia });
      setDesejo('');
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
      titulo="Wishlist"
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
            value={desejo}
            onChange={(e) => setDesejo(e.target.value)}
            placeholder="O que você quer"
            className={`${campo} w-full`}
            required
          />
          <div className="flex gap-2">
            <input
              type="number"
              step="0.01"
              min="0"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              placeholder="Valor"
              className={`${campo} w-28`}
              required
            />
            <select
              value={importancia}
              onChange={(e) => setImportancia(e.target.value as Importancia)}
              className={`${campo} flex-1`}
              aria-label="Importância"
            >
              <option value="alta">Alta</option>
              <option value="media">Média</option>
              <option value="baixa">Baixa</option>
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

      {pendentes.length === 0 ? (
        <p className="text-sm text-slate-400">Nenhum desejo na lista.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {pendentes.map((item) => (
            <li key={item.id} className="group flex items-center gap-3 py-2">
              <input
                type="checkbox"
                checked={item.somar}
                disabled={somenteLeitura}
                onChange={() => void aoAtualizar(item.id, { somar: !item.somar })}
                className="h-4 w-4 rounded border-slate-300"
                aria-label={`Somar ${item.desejo}`}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-slate-700">{item.desejo}</p>
              </div>
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                  ESTILO_IMPORTANCIA[item.importancia]
                }`}
              >
                {item.importancia}
              </span>
              <span className="tabular-nums text-sm font-medium text-slate-900">
                {moeda(item.valor)}
              </span>
              {!somenteLeitura && (
                <button
                  onClick={() => void aoExcluir(item.id)}
                  className="text-xs text-slate-300 opacity-0 hover:text-rose-600 group-hover:opacity-100"
                  aria-label={`Excluir ${item.desejo}`}
                >
                  ✕
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {marcados.length > 0 && (
        <div className="mt-3 border-t-2 border-slate-200 pt-3">
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">
              Selecionado
              <span className="ml-1 text-xs text-slate-400">
                ({marcados.length})
              </span>
            </span>
            <span className="tabular-nums font-semibold text-slate-900">
              {moeda(totalMarcado)}
            </span>
          </div>
          <p
            className={`mt-1 text-xs ${
              cabeNaReserva ? 'text-emerald-600' : 'text-rose-600'
            }`}
          >
            {cabeNaReserva
              ? `Cabe no guardado (${moeda(totalGuardado)}).`
              : `Faltam ${moeda(totalMarcado - Number(totalGuardado))} no guardado.`}
          </p>
        </div>
      )}
    </Card>
  );
}
