import { useCallback, useEffect, useState } from 'react';
import { api } from './lib/api';
import { NOMES_MESES } from './lib/formato';
import { useTema } from './lib/tema';
import { BotaoTema } from './components/BotaoTema';
import { CalendarioVencimentos } from './components/CalendarioVencimentos';
import { FormularioLancamento } from './components/FormularioLancamento';
import { GastosFixos } from './components/GastosFixos';
import { GastosPorCategoria } from './components/GastosPorCategoria';
import { GerenciadorAnos } from './components/GerenciadorAnos';
import { ImportarExtrato } from './components/ImportarExtrato';
import { Login } from './components/Login';
import { sessao } from './lib/sessao';
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
  ResumoAno,
} from './types/api';

export default function App() {
  const { tema, alternar } = useTema();

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
  const [importando, setImportando] = useState(false);
  // null = ainda verificando o token guardado.
  const [autenticado, setAutenticado] = useState<boolean | null>(null);

  // Confere se o token guardado ainda vale antes de mostrar a tela principal,
  // e volta ao login se a API derrubar a sessão a qualquer momento.
  useEffect(() => {
    sessao.observarExpiracao(() => setAutenticado(false));

    if (!sessao.ler()) {
      setAutenticado(false);
      return;
    }
    api
      .eu()
      .then(() => setAutenticado(true))
      .catch(() => setAutenticado(false));
  }, []);

  const carregarAnos = useCallback(async () => {
    const lista = await api.listarAnos();
    setAnos(lista);
    return lista;
  }, []);

  // Carga inicial: anos disponíveis e categorias. Só depois do login — antes
  // disso toda chamada voltaria 401.
  useEffect(() => {
    if (!autenticado) return;
    setCarregando(true);
    (async () => {
      try {
        const [listaAnos, listaCategorias] = await Promise.all([
          carregarAnos(),
          api.listarCategorias(),
        ]);
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
  }, [carregarAnos, autenticado]);

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
    if (!autenticado) return;
    void recarregar();
  }, [recarregar, autenticado]);

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

  /** Ações que mudam a lista de anos precisam recarregá-la, não só o resumo. */
  async function comAnos(operacao: () => Promise<unknown>, irPara?: number) {
    try {
      await operacao();
      await carregarAnos();
      if (irPara !== undefined) {
        setAnoAtual(irPara);
      } else {
        await recarregar();
      }
      setErro('');
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'A operação falhou.');
    }
  }

  if (autenticado === null) return <Aviso texto="Verificando sessão…" />;

  if (!autenticado) {
    return (
      <Login
        aoEntrar={() => {
          setErro('');
          setAutenticado(true);
        }}
      />
    );
  }

  if (carregando) return <Aviso texto="Carregando…" />;

  if (anoAtual === null) {
    return (
      <Aviso texto="Nenhum ano cadastrado. Crie o primeiro pela API em /docs." />
    );
  }

  const mes = resumo?.meses[mesAtual - 1];
  const arquivado = resumo?.arquivado ?? false;

  return (
    <div className="min-h-screen bg-roxo-50 dark:bg-roxo-950">
      <header className="border-b border-roxo-100 bg-white dark:border-roxo-700 dark:bg-roxo-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <h1 className="text-lg font-semibold text-roxo-600 dark:text-roxo-50">
            Planejamento Financeiro
          </h1>

          <GerenciadorAnos
            anos={anos}
            anoAtual={anoAtual}
            aoTrocar={setAnoAtual}
            aoCriar={(ano) => comAnos(() => api.criarAno(ano), ano)}
            aoArquivar={(ano) => comAnos(() => api.arquivarAno(ano))}
            aoDesarquivar={(ano) => comAnos(() => api.desarquivarAno(ano))}
          />

          <div className="ml-auto flex items-center gap-2">
            {!arquivado && (
              <button
                onClick={() => setImportando((v) => !v)}
                className="rounded-lg border border-roxo-200 px-3 py-1.5 text-xs font-medium text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
              >
                Importar extrato
              </button>
            )}
            <BotaoTema tema={tema} aoAlternar={alternar} />
            <button
              onClick={() => {
                api.sair();
                setAutenticado(false);
              }}
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
                    onClick={() => setMesAtual(numero)}
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

      <main className="mx-auto max-w-6xl px-6 py-6">
        {erro && (
          <p className="mb-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-200">
            {erro}
          </p>
        )}

        {importando && !arquivado && (
          <div className="mb-5">
            <ImportarExtrato
              ano={anoAtual}
              categorias={categorias}
              aoFechar={() => setImportando(false)}
              aoImportar={recarregar}
            />
          </div>
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

            <CalendarioVencimentos
              gastos={gastosFixos}
              ano={anoAtual}
              mes={mesAtual}
              somenteLeitura={arquivado}
              aoAlternar={alternarGastoFixo}
            />

            <Wishlist
              desejos={desejos}
              totalGuardado={resumo.total_guardado}
              somenteLeitura={arquivado}
              aoCriar={acao(api.criarDesejo)}
              aoAtualizar={acao(api.atualizarDesejo)}
              aoExcluir={acao(api.excluirDesejo)}
            />

            <div className="lg:col-span-3">
              {!arquivado && (
                <FormularioLancamento
                  ano={anoAtual}
                  mes={mesAtual}
                  categorias={categorias}
                  aoSalvar={acao(api.criarLancamento)}
                />
              )}
              <TabelaLancamentos
                titulo={NOMES_MESES[mesAtual - 1]}
                lancamentos={lancamentos}
                somenteLeitura={arquivado}
                aoExcluir={acao(api.excluirLancamento)}
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
    <div className="flex min-h-screen items-center justify-center bg-roxo-50 dark:bg-roxo-950">
      <p className="text-sm text-roxo-400 dark:text-roxo-200">{texto}</p>
    </div>
  );
}
