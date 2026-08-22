import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { api } from './lib/api';
import { useModoVisual } from './lib/modoVisual';
import { useTema } from './lib/tema';
import { Login } from './components/Login';
import { sessao } from './lib/sessao';
import { ModoPlanilha } from './pages/ModoPlanilha';
import type { PropsModo } from './pages/tiposModo';

/**
 * O painel entra sob demanda: ele carrega `react-grid-layout` e o Recharts,
 * que juntos pesam mais que todo o resto do app. Quem abre na planilha — o
 * caso comum, e no celular, em rede móvel — não deve pagar por eles.
 */
const ModoEstatico = lazy(() =>
  import('./pages/ModoEstatico').then((m) => ({ default: m.ModoEstatico })),
);
import type {
  Ano,
  Categoria,
  Conta,
  Desejo,
  Fatura,
  GastoFixo,
  Lancamento,
  ResumoAno,
} from './types/api';

export default function App() {
  const { tema, alternar } = useTema();
  const { modo, definir: definirModo } = useModoVisual();

  const [anos, setAnos] = useState<Ano[]>([]);
  const [anoAtual, setAnoAtual] = useState<number | null>(null);
  const [mesAtual, setMesAtual] = useState(new Date().getMonth() + 1);
  const [resumo, setResumo] = useState<ResumoAno | null>(null);
  const [lancamentos, setLancamentos] = useState<Lancamento[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [contas, setContas] = useState<Conta[]>([]);
  const [gastosFixos, setGastosFixos] = useState<GastoFixo[]>([]);
  const [desejos, setDesejos] = useState<Desejo[]>([]);
  const [faturas, setFaturas] = useState<Record<number, Fatura>>({});
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [importando, setImportando] = useState(false);
  const [editandoLancamento, setEditandoLancamento] = useState<Lancamento | null>(
    null,
  );
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
        const [listaAnos, listaCategorias, listaContas] = await Promise.all([
          carregarAnos(),
          api.listarCategorias(),
          api.listarContas(),
        ]);
        setCategorias(listaCategorias);
        setContas(listaContas);
        // Abre no ano corrente. Sem ele, cai no não arquivado mais recente —
        // e, se todos estiverem arquivados, no último. Antes abria sempre no
        // mais recente, então criar 2027 para planejar fazia o app abrir numa
        // tela vazia enquanto o ano em uso ficava escondido no seletor.
        const atual = new Date().getFullYear();
        const escolhido =
          listaAnos.find((a) => a.ano === atual) ??
          listaAnos.find((a) => !a.arquivado) ??
          listaAnos[0];
        setAnoAtual(escolhido?.ano ?? null);
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
      const [
        novoResumo,
        novosLancamentos,
        novosGastos,
        novosDesejos,
        novasContas,
      ] = await Promise.all([
        api.resumo(anoAtual),
        api.listarLancamentos(anoAtual, mesAtual),
        api.listarGastosFixos(anoAtual),
        api.listarWishlist(anoAtual),
        api.listarContas(),
      ]);
      setResumo(novoResumo);
      setLancamentos(novosLancamentos);
      setGastosFixos(novosGastos);
      setDesejos(novosDesejos);
      setContas(novasContas);

      const cartoes = novasContas.filter((c) => c.tipo === 'cartao_credito');
      const listaFaturas = await Promise.all(
        cartoes.map((c) => api.fatura(anoAtual, c.id, mesAtual)),
      );
      setFaturas(Object.fromEntries(listaFaturas.map((f) => [f.cartao_id, f])));

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

  /**
   * Categorias mudam fora do fluxo de `recarregar()` (que não as busca), e o
   * nome/cor delas aparece dentro de "Gastos por categoria" — por isso, além
   * de recarregar a lista, também refaz o resumo do mês.
   */
  async function aposMudarCategorias() {
    setCategorias(await api.listarCategorias());
    await recarregar();
  }

  async function criarCategoriaInline(nome: string) {
    const nova = await api.criarCategoria(nome);
    setCategorias((atual) => [...atual, nova]);
    return nova;
  }

  async function atualizarLancamento(
    id: number,
    dados: Partial<Parameters<typeof api.criarLancamento>[1]>,
  ) {
    if (anoAtual === null) return;
    await api.atualizarLancamento(anoAtual, id, dados);
    await recarregar();
  }

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

  // Os dois modos recebem exatamente o mesmo pacote: mostram o mesmo mês, com
  // as mesmas operações — só mudam o arranjo na tela.
  const propsModo: PropsModo = {
    tema,
    alternar,
    anos,
    anoAtual,
    setAnoAtual,
    mesAtual,
    setMesAtual,
    resumo,
    lancamentos,
    categorias,
    contas,
    gastosFixos,
    desejos,
    faturas,
    erro,
    setErro,
    importando,
    setImportando,
    editandoLancamento,
    setEditandoLancamento,
    recarregar,
    acao,
    alternarGastoFixo,
    aposMudarCategorias,
    criarCategoriaInline,
    atualizarLancamento,
    comAnos,
    modo,
    aoDefinirModo: definirModo,
    aoSair: () => {
      api.sair();
      setAutenticado(false);
    },
  };

  return modo === 'estatico' ? (
    <Suspense fallback={<Aviso texto="Carregando painel…" />}>
      <ModoEstatico {...propsModo} />
    </Suspense>
  ) : (
    <ModoPlanilha {...propsModo} />
  );
}

function Aviso({ texto }: { texto: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-roxo-50 dark:bg-roxo-950">
      <p className="text-sm text-roxo-400 dark:text-roxo-200">{texto}</p>
    </div>
  );
}
