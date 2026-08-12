import { useState, type FormEvent } from 'react';
import { Card } from './Card';
import { moeda } from '../lib/formato';
import type { CarteirasConta, Conta } from '../types/api';

interface Props {
  contas: Conta[];
  /** Fechamento atual de cada conta, para mostrar quanto há em cada uma. */
  posicao: CarteirasConta[];
  somenteLeitura: boolean;
  aoCriar: (nome: string, cor: string) => Promise<void>;
  aoExcluir: (id: number) => Promise<void>;
}

// Cores das marcas, para a conta ser reconhecível de relance.
const SUGESTOES = ['#8d7799', '#820ad1', '#00b1ea', '#f97316', '#22c55e'];

/** Container de contas: onde o dinheiro está, somando saldo e reserva. */
export function GerenciadorContas({
  contas,
  posicao,
  somenteLeitura,
  aoCriar,
  aoExcluir,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [nome, setNome] = useState('');
  const [cor, setCor] = useState(SUGESTOES[0]);
  const [erro, setErro] = useState('');

  const porConta = new Map(posicao.map((p) => [p.conta_id, p]));
  const patrimonio = posicao.reduce(
    (soma, p) => soma + Number(p.saldo) + Number(p.guardado),
    0,
  );

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');
    try {
      await aoCriar(nome, cor);
      setNome('');
      setAberto(false);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar.');
    }
  }

  const campo =
    'rounded-lg border border-roxo-100 px-3 py-2 text-sm focus:border-roxo-400 focus:outline-none dark:border-roxo-700 dark:focus:border-roxo-300';

  return (
    <Card
      titulo="Contas"
      acao={
        !somenteLeitura && (
          <button
            onClick={() => setAberto(!aberto)}
            className="text-xs font-medium text-roxo-400 hover:text-roxo-600 dark:text-roxo-200 dark:hover:text-roxo-50"
          >
            {aberto ? 'Cancelar' : '+ Nova'}
          </button>
        )
      }
    >
      {aberto && (
        <form onSubmit={enviar} className="mb-4 space-y-2">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome (ex.: Nubank)"
            className={`${campo} w-full`}
            required
          />
          <div className="flex items-center gap-2">
            {SUGESTOES.map((opcao) => (
              <button
                key={opcao}
                type="button"
                onClick={() => setCor(opcao)}
                aria-label={`Cor ${opcao}`}
                className={`h-6 w-6 rounded-full border-2 ${
                  cor === opcao
                    ? 'border-roxo-500 dark:border-roxo-100'
                    : 'border-transparent'
                }`}
                style={{ backgroundColor: opcao }}
              />
            ))}
            <button
              type="submit"
              className="ml-auto rounded-lg bg-roxo-500 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400"
            >
              Adicionar
            </button>
          </div>
          {erro && <p className="text-sm text-rose-600">{erro}</p>}
        </form>
      )}

      {contas.length === 0 ? (
        <p className="text-sm text-roxo-300">Nenhuma conta cadastrada.</p>
      ) : (
        <ul className="divide-y divide-roxo-100 dark:divide-roxo-700">
          {contas.map((conta) => {
            const p = porConta.get(conta.id);
            const saldo = Number(p?.saldo ?? 0);
            const guardado = Number(p?.guardado ?? 0);
            return (
              <li key={conta.id} className="group flex items-center gap-3 py-2">
                <span
                  className="h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: conta.cor }}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-roxo-600 dark:text-roxo-100">
                    {conta.nome}
                  </p>
                  {guardado !== 0 && (
                    <p className="text-xs text-roxo-300">
                      guardado: {moeda(guardado)}
                    </p>
                  )}
                </div>
                <span
                  className={`tabular-nums text-sm font-medium ${
                    saldo < 0
                      ? 'text-rose-600 dark:text-rose-400'
                      : 'text-roxo-700 dark:text-roxo-50'
                  }`}
                >
                  {moeda(saldo)}
                </span>
                {!somenteLeitura && (
                  <button
                    onClick={() => void aoExcluir(conta.id)}
                    className="text-xs text-roxo-200 opacity-0 hover:text-rose-600 group-hover:opacity-100"
                    aria-label={`Excluir ${conta.nome}`}
                  >
                    ✕
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {posicao.length > 0 && (
        <div className="mt-3 flex justify-between border-t-2 border-roxo-100 pt-3 text-sm dark:border-roxo-600">
          <span className="text-roxo-500 dark:text-roxo-200">
            Patrimônio
            <span className="ml-1 text-xs text-roxo-300">
              (saldo + guardado)
            </span>
          </span>
          <span className="tabular-nums font-semibold text-roxo-700 dark:text-roxo-50">
            {moeda(patrimonio)}
          </span>
        </div>
      )}
    </Card>
  );
}
