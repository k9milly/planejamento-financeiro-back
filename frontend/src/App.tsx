import { useCallback, useEffect, useState } from 'react';
import { api } from './lib/api';
import { NOMES_MESES } from './lib/formato';
import { FormularioLancamento } from './components/FormularioLancamento';
import { GastosFixos } from './components/GastosFixos';
import { GastosPorCategoria } from './components/GastosPorCategoria';
import { TabelaLancamentos } from './components/TabelaLancamentos';
import { TotaisMes } from './components/TotaisMes';
import { TotalGuardado } from './components/TotalGuardado';
import { Wishlist } from './components/Wishlist';
import type {
  Ano,
  Categoria,
  Desejo,
  GastoFixo,
  Lancamento,
  NovoLancamento,
  ResumoAno,
} from './types/api';

export default function App() {
  const [anos, setAnos] = useState<Ano[]>([]);
  const [anoAtual, setAnoAtual] = useState<number | null>(null);
  const [mesAtual, setMesAtual] = useState(new Date().getMonth() + 1);
  const [resumo, setResumo] = useState<ResumoAno | null>(null);
  const [lancamentos, setLancamentos] = useState<Lancamento[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [gastosFixos, setGastosFixos] = useState<GastoFixo[]>([]);
  const [desejos, setDesejos] = useState<Desejo[]>([]);
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(true);

  // Carga inicial: anos disponíveis e categorias.
  useEffect(() => {
    (async () => {
      try {
        const [listaAnos, listaCategorias] = await Promise.all([
          api.listarAnos(),
          api.listarCategorias(),
        ]);
        setAnos(listaAnos);
        setCategorias(listaCategorias);
        // Prefere um ano não arquivado; se todos estiverem, mostra o mais recente.
        const ativo = listaAnos.find((a) => !a.arquivado) ?? listaAnos[0];
        setAnoAtual(ativo?.ano ?? null);
      } catch (e) {
        setErro(e instanceof Error ? e.message : 'Falha ao carregar os dados.');
      } finally {
        setCarregando(false);
      }
    })();
  }, []);

  const recarregar = useCallback(async () => {
    if (anoAtual === null) return;
    try {
      const [novoResumo, novosLancamentos, novosGastos, novosDesejos] =
        await Promise.all([
          api.resumo(anoAtual),
          api.listarLancamentos(anoAtual, mesAtual),
          api.listarGastosFixos(anoAtual),
          api.listarWishlist(anoAtual),
        ]);
      setResumo(novoResumo);
      setLancamentos(novosLancamentos);
      setGastosFixos(novosGastos);
      setDesejos(novosDesejos);
      setErro('');
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao carregar o mês.');
    }
  }, [anoAtual, mesAtual]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  async function adicionar(dados: NovoLancamento) {
    if (anoAtual === null) return;
    await api.criarLancamento(anoAtual, dados);
    await recarregar();
  }

  async function excluir(id: number) {
    if (anoAtual === null) return;
    await api.excluirLancamento(anoAtual, id);
    await recarregar();
  }

  /** Envolve uma escrita: executa, recarrega tudo e mostra o erro na barra. */
  function acao<A extends unknown[]>(
    operacao: (ano: number, ...args: A) => Promise<unknown>,
  ) {
    return async (...args: A) => {
      if (anoAtual === null) return;
      try {
        await operacao(anoAtual, ...args);
        await recarregar();
      } catch (e) {
        setErro(e instanceof Error ? e.message : 'A operação falhou.');
        throw e;
      }
    };
  }

  const alternarGastoFixo = acao(
    async (ano: number, gasto: GastoFixo, pago: boolean) => {
      if (pago) {
        await api.pagarGastoFixo(ano, gasto.id, mesAtual);
      } else {
        await api.desfazerGastoFixo(ano, gasto.id, mesAtual);
      }
    },
  );

  if (carregando) {
    return <Aviso texto="Carregando…" />;
  }

  if (anoAtual === null) {
    return (
      <Aviso texto="Nenhum ano cadastrado. Crie o primeiro pela API em /docs." />
    );
  }

  const mes = resumo?.meses[mesAtual - 1];
  const arquivado = resumo?.arquivado ?? false;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-900">
            Planejamento Financeiro
          </h1>

          <select
            value={anoAtual}
            onChange={(e) => setAnoAtual(Number(e.target.value))}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm"
            aria-label="Ano"
          >
            {anos.map((a) => (
              <option key={a.id} value={a.ano}>
                {a.ano}
                {a.arquivado ? ' (arquivado)' : ''}
              </option>
            ))}
          </select>

          {arquivado && (
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800">
              Somente leitura
            </span>
          )}
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
                    onClick={() => setMesAtual(numero)}
                    aria-current={ativo ? 'page' : undefined}
                    className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
                      ativo
                        ? 'border-slate-900 font-medium text-slate-900'
                        : 'border-transparent text-slate-500 hover:text-slate-800'
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

      <main className="mx-auto max-w-6xl px-6 py-6">
        {erro && (
          <p className="mb-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {erro}
          </p>
        )}

        {resumo && mes && (
          <div className="grid gap-5 lg:grid-cols-3">
            <TotalGuardado resumo={resumo} />
            <TotaisMes mes={mes} />
            <GastosPorCategoria mes={mes} />

            <GastosFixos
              gastos={gastosFixos}
              categorias={categorias}
              mes={mesAtual}
              somenteLeitura={arquivado}
              aoCriar={acao(api.criarGastoFixo)}
              aoAlternar={alternarGastoFixo}
              aoExcluir={acao(api.excluirGastoFixo)}
            />

            <div className="lg:col-span-2">
              <Wishlist
                desejos={desejos}
                totalGuardado={resumo.total_guardado}
                somenteLeitura={arquivado}
                aoCriar={acao(api.criarDesejo)}
                aoAtualizar={acao(api.atualizarDesejo)}
                aoExcluir={acao(api.excluirDesejo)}
              />
            </div>

            <div className="lg:col-span-3">
              {!arquivado && (
                <FormularioLancamento
                  ano={anoAtual}
                  mes={mesAtual}
                  categorias={categorias}
                  aoSalvar={adicionar}
                />
              )}
              <TabelaLancamentos
                titulo={NOMES_MESES[mesAtual - 1]}
                lancamentos={lancamentos}
                somenteLeitura={arquivado}
                aoExcluir={excluir}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function Aviso({ texto }: { texto: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <p className="text-sm text-slate-500">{texto}</p>
    </div>
  );
}
