import { useEffect, useState, type ChangeEvent } from 'react';
import { api } from '../lib/api';
import { diaMes, ESTILO_FORMA_PAGAMENTO, ESTILO_TIPO, moeda } from '../lib/formato';
import type {
  Categoria,
  Conta,
  DestinoRendimento,
  FormaPagamento,
  PreviaImportacao,
  TipoLancamento,
  TransacaoConfirmar,
  TransacaoPrevia,
} from '../types/api';

interface Props {
  ano: number;
  categorias: Categoria[];
  contas: Conta[];
  aoFechar: () => void;
  aoImportar: () => Promise<void>;
}

/**
 * Transferência fica de fora: ela precisa de uma segunda conta, e o extrato de
 * um banco só mostra a perna que saiu. Para registrá-la, use o formulário do
 * mês, onde dá para escolher origem e destino.
 */
const TIPOS = (Object.keys(ESTILO_TIPO) as TipoLancamento[]).filter(
  (t) => t !== 'transferencia',
);

/** Tipos que precisam saber qual carteira foi afetada. */
const COM_DESTINO: TipoLancamento[] = ['rendimento', 'perda'];

const FORMAS_PAGAMENTO = Object.keys(ESTILO_FORMA_PAGAMENTO) as FormaPagamento[];

/** O que o usuário decidiu sobre cada linha da prévia. */
interface Escolha {
  incluir: boolean;
  tipo: TipoLancamento;
  categoriaId: string;
  destino: DestinoRendimento;
  // O extrato não diz a forma de pagamento — '' = não informado (vira null).
  formaPagamento: FormaPagamento | '';
  padrao: string;
}

/**
 * Importação de extrato OFX em duas etapas: prévia e confirmação.
 *
 * A revisão é obrigatória de propósito. O extrato não diz se um Pix recebido é
 * salário ou devolução de um amigo, nem que uma transferência para a poupança
 * é "guardado" e não uma saída comum — só quem gastou sabe.
 */
export function ImportarExtrato({
  ano,
  categorias,
  contas,
  aoFechar,
  aoImportar,
}: Props) {
  const [previa, setPrevia] = useState<PreviaImportacao | null>(null);
  const [escolhas, setEscolhas] = useState<Record<string, Escolha>>({});
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState('');
  const [resultado, setResultado] = useState('');
  // De qual conta é o extrato. Vale para todas as linhas do arquivo: um
  // extrato vem sempre de um banco só.
  const [contaId, setContaId] = useState('');

  useEffect(() => {
    if (!contaId && contas.length) setContaId(String(contas[0].id));
  }, [contas, contaId]);

  async function selecionarArquivo(evento: ChangeEvent<HTMLInputElement>) {
    const arquivo = evento.target.files?.[0];
    if (!arquivo) return;

    setErro('');
    setResultado('');
    setOcupado(true);
    try {
      const dados = await api.previaOfx(ano, arquivo);
      setPrevia(dados);
      setEscolhas(
        Object.fromEntries(
          dados.transacoes.map((t) => [
            t.fitid,
            {
              // Já importadas e de outro ano vêm desmarcadas: o padrão seguro é
              // não gravar de novo o que já está lá.
              incluir: !t.duplicado && !t.fora_do_ano,
              tipo: t.tipo_sugerido,
              categoriaId: t.categoria_sugerida_id
                ? String(t.categoria_sugerida_id)
                : '',
              destino: 'guardado',
              formaPagamento: '',
              padrao: '',
            },
          ]),
        ),
      );
    } catch (e) {
      setPrevia(null);
      setErro(e instanceof Error ? e.message : 'Não foi possível ler o arquivo.');
    } finally {
      setOcupado(false);
      // Permite reenviar o mesmo arquivo depois de corrigir algo.
      evento.target.value = '';
    }
  }

  function alterar(fitid: string, mudanca: Partial<Escolha>) {
    setEscolhas((atual) => ({
      ...atual,
      [fitid]: { ...atual[fitid], ...mudanca },
    }));
  }

  async function confirmar() {
    if (!previa) return;
    setOcupado(true);
    setErro('');
    try {
      const selecionadas: TransacaoConfirmar[] = previa.transacoes
        .filter((t) => escolhas[t.fitid]?.incluir)
        .map((t) => {
          const escolha = escolhas[t.fitid];
          const ehSaida = escolha.tipo === 'saida';
          return {
            fitid: t.fitid,
            conta_id: Number(contaId),
            data: t.data,
            valor: t.valor,
            tipo: escolha.tipo,
            // O backend recusa destino/categoria em tipos que não os aceitam.
            destino: COM_DESTINO.includes(escolha.tipo) ? escolha.destino : null,
            categoria_id:
              ehSaida && escolha.categoriaId ? Number(escolha.categoriaId) : null,
            forma_pagamento:
              ehSaida && escolha.formaPagamento ? escolha.formaPagamento : null,
            descricao: t.descricao,
            aprender_padrao:
              ehSaida && escolha.padrao.trim() && escolha.categoriaId
                ? escolha.padrao.trim()
                : null,
          };
        });

      const saida = await api.confirmarOfx(ano, selecionadas);
      await aoImportar();

      setPrevia(null);
      setResultado(
        `${saida.importadas} lançamento(s) importado(s)` +
          (saida.ignoradas_duplicadas
            ? `, ${saida.ignoradas_duplicadas} já existia(m)`
            : '') +
          (saida.regras_criadas
            ? `, ${saida.regras_criadas} regra(s) aprendida(s)`
            : '') +
          '.',
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'A importação falhou.');
    } finally {
      setOcupado(false);
    }
  }

  const marcadas = previa
    ? previa.transacoes.filter((t) => escolhas[t.fitid]?.incluir).length
    : 0;

  const campo =
    'rounded border border-roxo-100 px-2 py-1 text-xs dark:border-roxo-700';

  return (
    <div className="rounded-xl border border-roxo-100 bg-white shadow-sm dark:border-roxo-700 dark:bg-roxo-900">
      <header className="flex items-center justify-between border-b border-roxo-100 px-5 py-3 dark:border-roxo-700">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-roxo-400 dark:text-roxo-200">
          Importar extrato
        </h2>
        <button
          onClick={aoFechar}
          className="text-xs font-medium text-roxo-400 hover:text-roxo-600 dark:text-roxo-200 dark:hover:text-roxo-50"
        >
          Fechar
        </button>
      </header>

      <div className="p-5">
        {!previa && (
          <div className="space-y-3">
            <p className="text-sm text-roxo-500 dark:text-roxo-200">
              Baixe o extrato em <strong>OFX</strong> pelo aplicativo do banco e
              selecione o arquivo. Nada é gravado até você revisar e confirmar.
            </p>
            <label className="block text-sm text-roxo-500 dark:text-roxo-200">
              Conta deste extrato
              <select
                value={contaId}
                onChange={(e) => setContaId(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-roxo-100 px-3 py-2 text-sm dark:border-roxo-700"
              >
                {contas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nome}
                  </option>
                ))}
              </select>
            </label>
            <input
              type="file"
              accept=".ofx,application/x-ofx,text/plain"
              onChange={selecionarArquivo}
              disabled={ocupado || !contaId}
              aria-label="Arquivo OFX"
              className="block w-full text-sm text-roxo-500 file:mr-3 file:rounded-lg file:border-0 file:bg-roxo-500 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-roxo-400 dark:text-roxo-200"
            />
            {ocupado && (
              <p className="text-sm text-roxo-400">Lendo o extrato…</p>
            )}
          </div>
        )}

        {erro && (
          <p className="mt-3 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-200">
            {erro}
          </p>
        )}

        {resultado && (
          <p className="mt-3 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
            {resultado}
          </p>
        )}

        {previa && (
          <>
            <p className="mb-3 text-sm text-roxo-500 dark:text-roxo-200">
              {previa.total_lidas} transação(ões) no extrato
              {previa.ja_importadas > 0 && (
                <>
                  {' · '}
                  <span className="text-amber-700 dark:text-amber-300">
                    {previa.ja_importadas} já importada(s)
                  </span>
                </>
              )}
            </p>

            <div className="-mx-5 overflow-x-auto px-5">
              <table className="w-full min-w-[880px] text-sm">
                <thead>
                  <tr className="border-b border-roxo-100 text-left text-xs uppercase tracking-wide text-roxo-300 dark:border-roxo-700">
                    <th className="pb-2 font-medium">Incluir</th>
                    <th className="pb-2 font-medium">Data</th>
                    <th className="pb-2 font-medium">Descrição</th>
                    <th className="pb-2 text-right font-medium">Valor</th>
                    <th className="pb-2 font-medium">Tipo</th>
                    <th className="pb-2 font-medium">Categoria</th>
                    <th className="pb-2 font-medium">Pagamento</th>
                    <th className="pb-2 font-medium">Lembrar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-roxo-100 dark:divide-roxo-700">
                  {previa.transacoes.map((t) => (
                    <Linha
                      key={t.fitid}
                      transacao={t}
                      escolha={escolhas[t.fitid]}
                      categorias={categorias}
                      campo={campo}
                      aoAlterar={(m) => alterar(t.fitid, m)}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                onClick={() => void confirmar()}
                disabled={ocupado || marcadas === 0}
                className="rounded-lg bg-roxo-500 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400 disabled:opacity-50"
              >
                {ocupado ? 'Importando…' : `Importar ${marcadas} selecionada(s)`}
              </button>
              <button
                onClick={() => setPrevia(null)}
                disabled={ocupado}
                className="rounded-lg border border-roxo-200 px-4 py-2 text-sm font-medium text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
              >
                Cancelar
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Linha({
  transacao,
  escolha,
  categorias,
  campo,
  aoAlterar,
}: {
  transacao: TransacaoPrevia;
  escolha: Escolha | undefined;
  categorias: Categoria[];
  campo: string;
  aoAlterar: (mudanca: Partial<Escolha>) => void;
}) {
  if (!escolha) return null;

  const bloqueada = transacao.duplicado || transacao.fora_do_ano;

  return (
    <tr className={bloqueada ? 'opacity-50' : undefined}>
      <td className="py-2">
        <input
          type="checkbox"
          checked={escolha.incluir}
          disabled={transacao.duplicado}
          onChange={(e) => aoAlterar({ incluir: e.target.checked })}
          className="h-4 w-4 rounded border-roxo-200 dark:border-roxo-600"
          aria-label={`Incluir ${transacao.descricao}`}
        />
      </td>
      <td className="py-2 tabular-nums text-roxo-400 dark:text-roxo-200">
        {diaMes(transacao.data)}
      </td>
      <td className="max-w-[16rem] py-2 text-roxo-600 dark:text-roxo-100">
        <span className="block truncate" title={transacao.descricao}>
          {transacao.descricao || '—'}
        </span>
        {transacao.duplicado && (
          <span className="text-[10px] uppercase text-amber-700 dark:text-amber-300">
            já importada
          </span>
        )}
        {transacao.fora_do_ano && (
          <span className="text-[10px] uppercase text-rose-600 dark:text-rose-400">
            fora do ano
          </span>
        )}
        {transacao.possivel_repetido && !transacao.duplicado && (
          <span className="text-[10px] uppercase text-amber-700 dark:text-amber-300">
            confira: já existe um lançamento igual
          </span>
        )}
      </td>
      <td className="py-2 text-right tabular-nums font-medium text-roxo-700 dark:text-roxo-50">
        {moeda(transacao.valor)}
      </td>
      <td className="py-2">
        <select
          value={escolha.tipo}
          onChange={(e) =>
            aoAlterar({ tipo: e.target.value as TipoLancamento })
          }
          className={campo}
          aria-label={`Tipo de ${transacao.descricao}`}
        >
          {TIPOS.map((t) => (
            <option key={t} value={t}>
              {ESTILO_TIPO[t].rotulo}
            </option>
          ))}
        </select>
      </td>
      <td className="py-2">
        {escolha.tipo === 'saida' && (
          <select
            value={escolha.categoriaId}
            onChange={(e) => aoAlterar({ categoriaId: e.target.value })}
            className={campo}
            aria-label={`Categoria de ${transacao.descricao}`}
          >
            <option value="">Sem categoria</option>
            {categorias.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
        )}
        {/* Rendimento e perda precisam saber qual carteira mexeu. */}
        {COM_DESTINO.includes(escolha.tipo) && (
          <select
            value={escolha.destino}
            onChange={(e) =>
              aoAlterar({ destino: e.target.value as DestinoRendimento })
            }
            className={campo}
            aria-label={`Onde, em ${transacao.descricao}`}
          >
            <option value="guardado">No guardado</option>
            <option value="conta">Na conta</option>
          </select>
        )}
        {escolha.tipo !== 'saida' && !COM_DESTINO.includes(escolha.tipo) && (
          <span className="text-xs text-roxo-300">—</span>
        )}
      </td>
      <td className="py-2">
        {escolha.tipo === 'saida' ? (
          <select
            value={escolha.formaPagamento}
            onChange={(e) =>
              aoAlterar({ formaPagamento: e.target.value as FormaPagamento | '' })
            }
            className={campo}
            aria-label={`Forma de pagamento de ${transacao.descricao}`}
          >
            <option value="">Não informar</option>
            {FORMAS_PAGAMENTO.map((f) => (
              <option key={f} value={f}>
                {ESTILO_FORMA_PAGAMENTO[f].icone} {ESTILO_FORMA_PAGAMENTO[f].rotulo}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-xs text-roxo-300">—</span>
        )}
      </td>
      <td className="py-2">
        {/* Cria uma regra para categorizar sozinho nas próximas importações. */}
        {escolha.tipo === 'saida' && escolha.categoriaId ? (
          <input
            value={escolha.padrao}
            onChange={(e) => aoAlterar({ padrao: e.target.value })}
            placeholder="ex.: ifood"
            className={`${campo} w-28`}
            aria-label={`Lembrar categoria para ${transacao.descricao}`}
          />
        ) : (
          <span className="text-xs text-roxo-300">—</span>
        )}
      </td>
    </tr>
  );
}
