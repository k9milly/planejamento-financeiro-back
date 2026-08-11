import { useState, type FormEvent } from 'react';
import type {
  Categoria,
  DestinoRendimento,
  NovoLancamento,
  TipoLancamento,
} from '../types/api';
import { ESTILO_TIPO } from '../lib/formato';

interface Props {
  ano: number;
  mes: number;
  categorias: Categoria[];
  aoSalvar: (dados: NovoLancamento) => Promise<void>;
}

const TIPOS = Object.keys(ESTILO_TIPO) as TipoLancamento[];

/** Formulário de novo lançamento, embutido acima da tabela do mês. */
export function FormularioLancamento({ ano, mes, categorias, aoSalvar }: Props) {
  const [tipo, setTipo] = useState<TipoLancamento>('saida');
  const [valor, setValor] = useState('');
  const [dia, setDia] = useState('1');
  const [categoriaId, setCategoriaId] = useState('');
  const [destino, setDestino] = useState<DestinoRendimento>('guardado');
  const [descricao, setDescricao] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');
    setSalvando(true);
    try {
      await aoSalvar({
        data: `${ano}-${String(mes).padStart(2, '0')}-${dia.padStart(2, '0')}`,
        valor,
        tipo,
        // O backend recusa destino/categoria em tipos que não os aceitam.
        destino: tipo === 'rendimento' ? destino : null,
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
    'rounded-lg border border-roxo-100 dark:border-roxo-700 px-3 py-2 text-sm focus:border-roxo-400 dark:focus:border-roxo-300 focus:outline-none';

  return (
    <form onSubmit={enviar} className="mb-4 space-y-3">
      <div className="flex flex-wrap gap-2">
        <input
          type="number"
          min="1"
          max="31"
          value={dia}
          onChange={(e) => setDia(e.target.value)}
          className={`${campo} w-20`}
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

        {tipo === 'rendimento' && (
          <select
            value={destino}
            onChange={(e) => setDestino(e.target.value as DestinoRendimento)}
            className={campo}
            aria-label="Destino do rendimento"
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
          className={`${campo} w-32`}
          aria-label="Valor"
          required
        />
        <input
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          placeholder="Descrição"
          className={`${campo} min-w-[10rem] flex-1`}
          aria-label="Descrição"
        />
        <button
          type="submit"
          disabled={salvando}
          className="rounded-lg bg-roxo-500 dark:bg-roxo-400 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400 disabled:opacity-50"
        >
          {salvando ? 'Salvando…' : 'Adicionar'}
        </button>
      </div>

      {erro && <p className="text-sm text-rose-600">{erro}</p>}
    </form>
  );
}
