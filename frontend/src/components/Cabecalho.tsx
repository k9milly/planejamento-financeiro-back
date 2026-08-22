import type { ReactNode } from 'react';
import { NOMES_MESES } from '../lib/formato';
import type { ModoVisual } from '../lib/modoVisual';
import type { Tema } from '../lib/tema';
import { BotaoTema } from './BotaoTema';
import { GerenciadorAnos } from './GerenciadorAnos';
import type { Ano } from '../types/api';

interface Props {
  tema: Tema;
  aoAlternarTema: () => void;
  anos: Ano[];
  anoAtual: number;
  aoTrocarAno: (ano: number) => void;
  aoCriarAno: (ano: number) => Promise<void>;
  aoArquivarAno: (ano: number) => Promise<void>;
  aoDesarquivarAno: (ano: number) => Promise<void>;
  mesAtual: number;
  aoTrocarMes: (mes: number) => void;
  modo: ModoVisual;
  aoDefinirModo: (modo: ModoVisual) => void;
  aoSair: () => void;
  /** Botões específicos do modo, à esquerda dos controles comuns. */
  acoes?: ReactNode;
}

/**
 * Barra superior compartilhada pelos dois modos: ano, mês, modo e tema.
 *
 * Cada modo a renderiza com suas próprias `acoes` (importar extrato na
 * planilha, editar layout no painel). O ano e o mês selecionados vivem em
 * `App.tsx`, acima dos dois — por isso trocar de modo não perde o lugar,
 * mesmo desmontando esta barra junto com o modo antigo.
 */
export function Cabecalho({
  tema,
  aoAlternarTema,
  anos,
  anoAtual,
  aoTrocarAno,
  aoCriarAno,
  aoArquivarAno,
  aoDesarquivarAno,
  mesAtual,
  aoTrocarMes,
  modo,
  aoDefinirModo,
  aoSair,
  acoes,
}: Props) {
  return (
    <header className="border-b border-roxo-100 bg-white dark:border-roxo-700 dark:bg-roxo-900">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
        <h1 className="text-lg font-semibold text-roxo-600 dark:text-roxo-50">
          Planejamento Financeiro
        </h1>

        <GerenciadorAnos
          anos={anos}
          anoAtual={anoAtual}
          aoTrocar={aoTrocarAno}
          aoCriar={aoCriarAno}
          aoArquivar={aoArquivarAno}
          aoDesarquivar={aoDesarquivarAno}
        />

        <div className="ml-auto flex items-center gap-2">
          {acoes}

          <SeletorModo modo={modo} aoDefinir={aoDefinirModo} />

          <BotaoTema tema={tema} aoAlternar={aoAlternarTema} />
          <button
            onClick={aoSair}
            className="rounded-lg border border-roxo-200 px-3 py-1.5 text-xs font-medium text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
          >
            Sair
          </button>
        </div>
      </div>

      {/* As 12 páginas do ano. */}
      <nav className="mx-auto max-w-6xl overflow-x-auto px-6">
        <ul className="flex gap-1 pb-px">
          {NOMES_MESES.map((nome, indice) => {
            const numero = indice + 1;
            const ativo = numero === mesAtual;
            return (
              <li key={nome}>
                <button
                  onClick={() => aoTrocarMes(numero)}
                  aria-current={ativo ? 'page' : undefined}
                  className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
                    ativo
                      ? 'border-roxo-500 font-medium text-roxo-600 dark:border-roxo-200 dark:text-roxo-50'
                      : 'border-transparent text-roxo-400 hover:text-roxo-600 dark:text-roxo-200 dark:hover:text-roxo-50'
                  }`}
                >
                  {nome}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}

/**
 * Alterna planilha/painel. Dois botões visíveis em vez de um que troca de
 * rótulo: com um só, não dá para saber se o texto diz onde você está ou para
 * onde você vai.
 */
function SeletorModo({
  modo,
  aoDefinir,
}: {
  modo: ModoVisual;
  aoDefinir: (modo: ModoVisual) => void;
}) {
  const opcoes: { valor: ModoVisual; rotulo: string }[] = [
    { valor: 'planilha', rotulo: 'Planilha' },
    { valor: 'estatico', rotulo: 'Painel' },
  ];

  return (
    <div
      role="group"
      aria-label="Modo de visualização"
      className="flex overflow-hidden rounded-lg border border-roxo-200 dark:border-roxo-600"
    >
      {opcoes.map(({ valor, rotulo }) => (
        <button
          key={valor}
          onClick={() => aoDefinir(valor)}
          aria-pressed={modo === valor}
          className={`px-3 py-1.5 text-xs font-medium ${
            modo === valor
              ? 'bg-roxo-500 text-white dark:bg-roxo-400'
              : 'text-roxo-500 hover:bg-roxo-100 dark:text-roxo-100 dark:hover:bg-roxo-700'
          }`}
        >
          {rotulo}
        </button>
      ))}
    </div>
  );
}
