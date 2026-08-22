import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import type {
  Categoria,
  Conta,
  DestinoRendimento,
  FormaPagamento,
  Lancamento,
  NovoLancamento,
  TipoLancamento,
} from '../types/api';
import { ESTILO_FORMA_PAGAMENTO, ESTILO_TIPO } from '../lib/formato';

interface Props {
  ano: number;
  mes: number;
  contas: Conta[];
  categorias: Categoria[];
  aoSalvar: (dados: NovoLancamento) => Promise<void>;
  aoCriarCategoria: (nome: string) => Promise<Categoria>;
  /** Presente = formulário em modo edição, pré-preenchido com este lançamento. */
  lancamento?: Lancamento | null;
  aoAtualizar?: (id: number, dados: Partial<NovoLancamento>) => Promise<void>;
  aoCancelar?: () => void;
  /** Botão de engrenagem + painel para criar/editar/excluir categorias. */
  menuCategorias?: ReactNode;
  /** Botão de engrenagem + painel para editar as cores da forma de pagamento. */
  menuFormaPagamento?: ReactNode;
}

const TIPOS = Object.keys(ESTILO_TIPO) as TipoLancamento[];
const FORMAS_PAGAMENTO = Object.keys(ESTILO_FORMA_PAGAMENTO) as FormaPagamento[];

/** Tipos que precisam saber qual carteira foi afetada. */
const COM_DESTINO: TipoLancamento[] = ['rendimento', 'perda'];

/** Sentinela do "+ nova categoria" dentro do <select>; nunca é um id de verdade. */
const NOVA_CATEGORIA = '__nova__';

/**
 * Formulário de lançamento: cria um novo, ou edita um existente quando
 * `lancamento` é passado.
 *
 * O componente que o renderiza deve usar `key={lancamento?.id ?? 'novo'}`
 * para forçar remontagem ao trocar de alvo — mais simples e menos propenso a
 * erro do que sincronizar cada campo via `useEffect` toda vez que o
 * lançamento sendo editado muda.
 */
export function FormularioLancamento({
  ano,
  mes,
  contas,
  categorias,
  aoSalvar,
  aoCriarCategoria,
  lancamento,
  aoAtualizar,
  aoCancelar,
  menuCategorias,
  menuFormaPagamento,
}: Props) {
  const editando = lancamento ?? null;

  const [tipo, setTipo] = useState<TipoLancamento>(editando?.tipo ?? 'saida');
  const [valor, setValor] = useState(editando?.valor ?? '');
  const [dia, setDia] = useState(
    editando ? String(Number(editando.data.split('-')[2])) : '',
  );
  const [contaId, setContaId] = useState(
    editando ? String(editando.conta_id) : '',
  );
  const [contaDestinoId, setContaDestinoId] = useState(
    editando?.conta_destino_id ? String(editando.conta_destino_id) : '',
  );
  const [categoriaId, setCategoriaId] = useState(
    editando?.categoria_id ? String(editando.categoria_id) : '',
  );
  const [destino, setDestino] = useState<DestinoRendimento>(
    editando?.destino ?? 'guardado',
  );
  // Pré-selecionado em débito para incentivar o preenchimento, sem tornar o
  // campo obrigatório no backend (ver ADR-0001).
  const [formaPagamento, setFormaPagamento] = useState<FormaPagamento>(
    editando?.forma_pagamento ?? 'debito',
  );
  const [descricao, setDescricao] = useState(editando?.descricao ?? '');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  // Criação de categoria embutida no seletor.
  const [criandoCategoria, setCriandoCategoria] = useState(false);
  const [nomeNovaCategoria, setNomeNovaCategoria] = useState('');

  const ehSaida = tipo === 'saida';
  const ehCredito = ehSaida && formaPagamento === 'credito';
  // Crédito só pode sair de um cartão; o resto (inclusive as outras formas de
  // pagamento) só pode sair de uma conta corrente (ver ADR-0002).
  const contasCompativeis = contas.filter((c) =>
    ehCredito ? c.tipo === 'cartao_credito' : c.tipo === 'corrente',
  );

  // Seleciona a primeira conta compatível assim que a lista chega, e troca de
  // novo se a conta escolhida deixar de ser compatível (ex.: mudou pra crédito).
  useEffect(() => {
    if (contasCompativeis.some((c) => String(c.id) === contaId)) return;
    setContaId(contasCompativeis.length ? String(contasCompativeis[0].id) : '');
  }, [contasCompativeis, contaId]);

  const ehTransferencia = tipo === 'transferencia';
  const outrasContas = contas.filter((c) => String(c.id) !== contaId);

  async function criarCategoriaInline() {
    const nome = nomeNovaCategoria.trim();
    if (!nome) return;
    try {
      const nova = await aoCriarCategoria(nome);
      setCategoriaId(String(nova.id));
      setCriandoCategoria(false);
      setNomeNovaCategoria('');
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível criar a categoria.');
    }
  }

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');

    if (ehTransferencia && !contaDestinoId) {
      setErro('Escolha a conta de destino da transferência.');
      return;
    }
    if (!contaId) {
      setErro(
        ehCredito
          ? 'Cadastre um cartão de crédito antes de lançar no crédito.'
          : 'Cadastre uma conta antes de lançar.',
      );
      return;
    }

    // Ao editar, o dia digitado vale dentro do ANO-MÊS do próprio lançamento
    // — não do mês que estava aberto na tela quando o formulário abriu. Sem
    // isso, editar um lançamento antigo enquanto se vê o mês atual movia a
    // data dele para o mês atual silenciosamente.
    const [anoBase, mesBase] = editando
      ? editando.data.split('-')
      : [String(ano), String(mes).padStart(2, '0')];

    const dados: NovoLancamento = {
      data: `${anoBase}-${mesBase}-${dia.padStart(2, '0')}`,
      valor,
      tipo,
      conta_id: Number(contaId),
      // O backend recusa campos que não pertencem ao tipo escolhido.
      conta_destino_id: ehTransferencia ? Number(contaDestinoId) : null,
      destino: COM_DESTINO.includes(tipo) ? destino : null,
      categoria_id: tipo === 'saida' && categoriaId ? Number(categoriaId) : null,
      forma_pagamento: ehSaida ? formaPagamento : null,
      descricao,
    };

    setSalvando(true);
    try {
      if (editando && aoAtualizar) {
        await aoAtualizar(editando.id, dados);
        aoCancelar?.();
      } else {
        await aoSalvar(dados);
        setValor('');
        setDescricao('');
      }
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar.');
    } finally {
      setSalvando(false);
    }
  }

  const campo =
    'rounded-lg border border-roxo-100 px-3 py-2 text-sm focus:border-roxo-400 focus:outline-none dark:border-roxo-700 dark:focus:border-roxo-300';

  return (
    <form
      onSubmit={enviar}
      className={
        editando
          ? 'mb-4 space-y-3 rounded-lg border border-roxo-300 p-3 dark:border-roxo-500'
          : 'mb-4 space-y-3'
      }
    >
      <div className="flex flex-wrap gap-2">
        <input
          type="number"
          min="1"
          max="31"
          value={dia}
          onChange={(e) => setDia(e.target.value)}
          placeholder="Dia"
          className={`${campo} w-16`}
          aria-label="Dia"
          required
        />
        <select
          value={tipo}
          onChange={(e) => setTipo(e.target.value as TipoLancamento)}
          className={campo}
          aria-label="Tipo"
        >
          {TIPOS.map((t) => (
            <option key={t} value={t}>
              {ESTILO_TIPO[t].rotulo}
            </option>
          ))}
        </select>

        <select
          value={contaId}
          onChange={(e) => setContaId(e.target.value)}
          className={campo}
          aria-label={ehTransferencia ? 'Conta de origem' : 'Conta'}
          required
        >
          {contasCompativeis.length === 0 && (
            <option value="" disabled>
              {ehCredito ? 'Nenhum cartão cadastrado' : 'Nenhuma conta cadastrada'}
            </option>
          )}
          {contasCompativeis.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}
            </option>
          ))}
        </select>

        {ehTransferencia && (
          <select
            value={contaDestinoId}
            onChange={(e) => setContaDestinoId(e.target.value)}
            className={campo}
            aria-label="Conta de destino"
            required
          >
            <option value="">Para…</option>
            {outrasContas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
        )}

        {ehSaida && !criandoCategoria && (
          <span className="flex items-center gap-1">
            <select
              value={categoriaId}
              onChange={(e) => {
                if (e.target.value === NOVA_CATEGORIA) {
                  setCriandoCategoria(true);
                  return;
                }
                setCategoriaId(e.target.value);
              }}
              className={campo}
              aria-label="Categoria"
            >
              <option value="">Sem categoria</option>
              {categorias.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
              <option value={NOVA_CATEGORIA}>+ Nova categoria…</option>
            </select>
            {menuCategorias}
          </span>
        )}

        {ehSaida && criandoCategoria && (
          <span className="flex items-center gap-1">
            <input
              value={nomeNovaCategoria}
              onChange={(e) => setNomeNovaCategoria(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void criarCategoriaInline();
                }
                if (e.key === 'Escape') setCriandoCategoria(false);
              }}
              placeholder="Nome da categoria"
              autoFocus
              className={`${campo} w-36`}
              aria-label="Nome da nova categoria"
            />
            <button
              type="button"
              onClick={() => void criarCategoriaInline()}
              className="rounded-lg bg-roxo-500 px-2 py-2 text-xs font-medium text-white hover:bg-roxo-400"
            >
              Criar
            </button>
            <button
              type="button"
              onClick={() => setCriandoCategoria(false)}
              className="text-xs text-roxo-300 hover:text-roxo-500"
            >
              Cancelar
            </button>
          </span>
        )}

        {ehSaida && (
          <span className="flex items-center gap-1">
            <select
              value={formaPagamento}
              onChange={(e) => setFormaPagamento(e.target.value as FormaPagamento)}
              className={campo}
              aria-label="Forma de pagamento"
            >
              {FORMAS_PAGAMENTO.map((f) => (
                <option key={f} value={f}>
                  {ESTILO_FORMA_PAGAMENTO[f].rotulo}
                </option>
              ))}
            </select>
            {menuFormaPagamento}
          </span>
        )}

        {COM_DESTINO.includes(tipo) && (
          <select
            value={destino}
            onChange={(e) => setDestino(e.target.value as DestinoRendimento)}
            className={campo}
            aria-label="Onde"
          >
            <option value="guardado">No guardado</option>
            <option value="conta">Na conta</option>
          </select>
        )}

        <input
          type="number"
          step="0.01"
          min="0.01"
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          placeholder="Valor"
          className={`${campo} w-28`}
          aria-label="Valor"
          required
        />
        <input
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          placeholder="Descrição"
          className={`${campo} min-w-[9rem] flex-1`}
          aria-label="Descrição"
        />
        <button
          type="submit"
          disabled={salvando || !contaId}
          className="rounded-lg bg-roxo-500 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400 disabled:opacity-50"
        >
          {salvando ? 'Salvando…' : editando ? 'Salvar' : 'Adicionar'}
        </button>
        {editando && (
          <button
            type="button"
            onClick={aoCancelar}
            className="rounded-lg border border-roxo-200 px-4 py-2 text-sm font-medium text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
          >
            Cancelar
          </button>
        )}
      </div>

      {erro && <p className="text-sm text-rose-600">{erro}</p>}
    </form>
  );
}
