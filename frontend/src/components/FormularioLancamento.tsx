import { useEffect, useState, type FormEvent } from 'react';
import type {
  Categoria,
  Conta,
  DestinoRendimento,
  NovoLancamento,
  TipoLancamento,
} from '../types/api';
import { ESTILO_TIPO } from '../lib/formato';

interface Props {
  ano: number;
  mes: number;
  contas: Conta[];
  categorias: Categoria[];
  aoSalvar: (dados: NovoLancamento) => Promise<void>;
}

const TIPOS = Object.keys(ESTILO_TIPO) as TipoLancamento[];

/** Tipos que precisam saber qual carteira foi afetada. */
const COM_DESTINO: TipoLancamento[] = ['rendimento', 'perda'];

/** Formulário de novo lançamento, embutido acima da tabela do mês. */
export function FormularioLancamento({
  ano,
  mes,
  contas,
  categorias,
  aoSalvar,
}: Props) {
  const [tipo, setTipo] = useState<TipoLancamento>('saida');
  const [valor, setValor] = useState('');
  const [dia, setDia] = useState('1');
  const [contaId, setContaId] = useState('');
  const [contaDestinoId, setContaDestinoId] = useState('');
  const [categoriaId, setCategoriaId] = useState('');
  const [destino, setDestino] = useState<DestinoRendimento>('guardado');
  const [descricao, setDescricao] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  // Seleciona a primeira conta assim que a lista chega.
  useEffect(() => {
    if (!contaId && contas.length) setContaId(String(contas[0].id));
  }, [contas, contaId]);

  const ehTransferencia = tipo === 'transferencia';
  const outrasContas = contas.filter((c) => String(c.id) !== contaId);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');

    if (ehTransferencia && !contaDestinoId) {
      setErro('Escolha a conta de destino da transferência.');
      return;
    }

    setSalvando(true);
    try {
      await aoSalvar({
        data: `${ano}-${String(mes).padStart(2, '0')}-${dia.padStart(2, '0')}`,
        valor,
        tipo,
        conta_id: Number(contaId),
        // O backend recusa campos que não pertencem ao tipo escolhido.
        conta_destino_id: ehTransferencia ? Number(contaDestinoId) : null,
        destino: COM_DESTINO.includes(tipo) ? destino : null,
        categoria_id:
          tipo === 'saida' && categoriaId ? Number(categoriaId) : null,
        descricao,
      });
      setValor('');
      setDescricao('');
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar.');
    } finally {
      setSalvando(false);
    }
  }

  const campo =
    'rounded-lg border border-roxo-100 px-3 py-2 text-sm focus:border-roxo-400 focus:outline-none dark:border-roxo-700 dark:focus:border-roxo-300';

  return (
    <form onSubmit={enviar} className="mb-4 space-y-3">
      <div className="flex flex-wrap gap-2">
        <input
          type="number"
          min="1"
          max="31"
          value={dia}
          onChange={(e) => setDia(e.target.value)}
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
          {contas.map((c) => (
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

        {tipo === 'saida' && (
          <select
            value={categoriaId}
            onChange={(e) => setCategoriaId(e.target.value)}
            className={campo}
            aria-label="Categoria"
          >
            <option value="">Sem categoria</option>
            {categorias.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
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
          {salvando ? 'Salvando…' : 'Adicionar'}
        </button>
      </div>

      {erro && <p className="text-sm text-rose-600">{erro}</p>}
    </form>
  );
}
