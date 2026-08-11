import { useState } from 'react';
import type { Ano } from '../types/api';

interface Props {
  anos: Ano[];
  anoAtual: number;
  aoTrocar: (ano: number) => void;
  aoCriar: (ano: number) => Promise<void>;
  aoArquivar: (ano: number) => Promise<void>;
  aoDesarquivar: (ano: number) => Promise<void>;
}

/**
 * Seletor de ano com as ações de arquivar, reabrir e criar.
 *
 * Arquivar é irreversível na prática (reabrir não recalcula os saldos já
 * propagados), então pede confirmação explícita descrevendo o efeito.
 */
export function GerenciadorAnos({
  anos,
  anoAtual,
  aoTrocar,
  aoCriar,
  aoArquivar,
  aoDesarquivar,
}: Props) {
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const atual = anos.find((a) => a.ano === anoAtual);
  const proximo = Math.max(...anos.map((a) => a.ano)) + 1;
  const proximoExiste = anos.some((a) => a.ano === proximo);

  async function executar(operacao: () => Promise<void>) {
    setOcupado(true);
    try {
      await operacao();
    } finally {
      setOcupado(false);
      setConfirmando(false);
    }
  }

  const botao =
    'rounded-lg border border-roxo-200 px-3 py-1.5 text-xs font-medium text-roxo-500 hover:bg-roxo-100 disabled:opacity-50 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700';

  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        value={anoAtual}
        onChange={(e) => aoTrocar(Number(e.target.value))}
        className="rounded-lg border border-roxo-100 px-3 py-1.5 text-sm dark:border-roxo-700"
        aria-label="Ano"
      >
        {anos.map((a) => (
          <option key={a.id} value={a.ano}>
            {a.ano}
            {a.arquivado ? ' (arquivado)' : ''}
          </option>
        ))}
      </select>

      {atual?.arquivado ? (
        <>
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800 dark:bg-amber-900 dark:text-amber-200">
            Somente leitura
          </span>
          <button
            className={botao}
            disabled={ocupado}
            onClick={() => void executar(() => aoDesarquivar(anoAtual))}
          >
            Reabrir
          </button>
        </>
      ) : (
        <button
          className={botao}
          disabled={ocupado}
          onClick={() => setConfirmando(true)}
        >
          Arquivar {anoAtual}
        </button>
      )}

      {!proximoExiste && (
        <button
          className={botao}
          disabled={ocupado}
          onClick={() => void executar(() => aoCriar(proximo))}
          title={`Criar ${proximo} para começar a planejar`}
        >
          + Criar {proximo}
        </button>
      )}

      {confirmando && (
        <div className="w-full rounded-lg border border-roxo-200 bg-roxo-50 p-3 text-sm dark:border-roxo-600 dark:bg-roxo-800">
          <p className="text-roxo-600 dark:text-roxo-100">
            Arquivar <strong>{anoAtual}</strong> deixa o ano somente leitura e
            prepara {anoAtual + 1} com o saldo e o guardado de fechamento como
            abertura. Você pode reabrir depois, mas os saldos já propagados não
            são recalculados sozinhos.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              className="rounded-lg bg-roxo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-roxo-400 disabled:opacity-50"
              disabled={ocupado}
              onClick={() => void executar(() => aoArquivar(anoAtual))}
            >
              {ocupado ? 'Arquivando…' : 'Arquivar'}
            </button>
            <button
              className={botao}
              disabled={ocupado}
              onClick={() => setConfirmando(false)}
            >
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
