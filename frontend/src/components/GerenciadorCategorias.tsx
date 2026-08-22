import { useState } from 'react';
import { Card } from './Card';
import type { Categoria } from '../types/api';

interface Props {
  categorias: Categoria[];
  somenteLeitura: boolean;
  aoCriar: (nome: string, cor: string) => Promise<void>;
  aoRenomear: (id: number, nome: string) => Promise<void>;
  aoMudarCor: (id: number, cor: string) => Promise<void>;
  aoExcluir: (id: number) => Promise<void>;
}

const SUGESTOES = ['#94a3b8', '#f97316', '#ec4899', '#0ea5e9', '#22c55e', '#8b5cf6'];

/**
 * Container de categorias: criar, renomear, trocar a cor, excluir.
 *
 * Renomear é editado no lugar (clique no nome vira um campo de texto) em vez
 * de um modal separado — é uma edição pequena, não precisa de mais cerimônia
 * que isso.
 */
export function GerenciadorCategorias({
  categorias,
  somenteLeitura,
  aoCriar,
  aoRenomear,
  aoMudarCor,
  aoExcluir,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [nome, setNome] = useState('');
  const [cor, setCor] = useState(SUGESTOES[0]);
  const [erro, setErro] = useState('');
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [nomeEditado, setNomeEditado] = useState('');

  async function enviar() {
    setErro('');
    if (!nome.trim()) return;
    try {
      await aoCriar(nome, cor);
      setNome('');
      setAberto(false);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar.');
    }
  }

  function iniciarEdicao(categoria: Categoria) {
    setEditandoId(categoria.id);
    setNomeEditado(categoria.nome);
  }

  async function confirmarEdicao(id: number) {
    const novoNome = nomeEditado.trim();
    setEditandoId(null);
    if (novoNome) await aoRenomear(id, novoNome);
  }

  const campo =
    'rounded-lg border border-roxo-100 px-3 py-2 text-sm focus:border-roxo-400 focus:outline-none dark:border-roxo-700 dark:focus:border-roxo-300';

  return (
    <Card
      titulo="Categorias"
      acao={
        !somenteLeitura && (
          <button
            type="button"
            onClick={() => setAberto(!aberto)}
            className="text-xs font-medium text-roxo-400 hover:text-roxo-600 dark:text-roxo-200 dark:hover:text-roxo-50"
          >
            {aberto ? 'Cancelar' : '+ Nova'}
          </button>
        )
      }
    >
      {/*
       * Div, não <form>: este painel é renderizado dentro do <form> do
       * lançamento (via popover), e um <form> aninhado é inválido em HTML —
       * o navegador colapsa os dois, e o botão "Adicionar" daqui acabava
       * disparando a validação nativa do formulário de fora.
       */}
      {aberto && (
        <div className="mb-4 space-y-2">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void enviar();
              }
            }}
            placeholder="Nome (ex.: Farmácia)"
            className={`${campo} w-full`}
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
              type="button"
              onClick={() => void enviar()}
              className="ml-auto rounded-lg bg-roxo-500 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400"
            >
              Adicionar
            </button>
          </div>
          {erro && <p className="text-sm text-rose-600">{erro}</p>}
        </div>
      )}

      {categorias.length === 0 ? (
        <p className="text-sm text-roxo-300">Nenhuma categoria cadastrada.</p>
      ) : (
        <ul className="divide-y divide-roxo-100 dark:divide-roxo-700">
          {categorias.map((categoria) => (
            <li key={categoria.id} className="group flex items-center gap-3 py-2">
              <input
                type="color"
                value={categoria.cor}
                disabled={somenteLeitura}
                onChange={(e) => void aoMudarCor(categoria.id, e.target.value)}
                className="h-6 w-6 shrink-0 cursor-pointer rounded-full border-0 bg-transparent p-0"
                aria-label={`Cor de ${categoria.nome}`}
              />
              {editandoId === categoria.id ? (
                <input
                  value={nomeEditado}
                  onChange={(e) => setNomeEditado(e.target.value)}
                  onBlur={() => void confirmarEdicao(categoria.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void confirmarEdicao(categoria.id);
                    }
                    if (e.key === 'Escape') setEditandoId(null);
                  }}
                  autoFocus
                  className={`${campo} flex-1 py-1`}
                />
              ) : (
                <button
                  type="button"
                  disabled={somenteLeitura}
                  onClick={() => iniciarEdicao(categoria)}
                  className="flex-1 truncate text-left text-sm text-roxo-600 hover:underline dark:text-roxo-100"
                  title="Clique para renomear"
                >
                  {categoria.nome}
                </button>
              )}
              {!somenteLeitura && (
                <button
                  type="button"
                  onClick={() => void aoExcluir(categoria.id)}
                  className="text-xs text-roxo-200 opacity-0 hover:text-rose-600 group-hover:opacity-100"
                  aria-label={`Excluir ${categoria.nome}`}
                >
                  ✕
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
