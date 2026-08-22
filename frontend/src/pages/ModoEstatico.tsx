import { useCallback, useEffect, useRef, useState } from 'react';
import { ResponsiveGridLayout, type Layout } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import { api } from '../lib/api';
import {
  adicionar,
  interpretar,
  layoutLocal,
  LAYOUT_PADRAO,
  serializar,
  widgetsDisponiveis,
  type ItemLayout,
} from '../lib/layoutDashboard';
import { CATALOGO, type ContextoWidget, type IdWidget } from '../components/widgets/catalogo';
import { Cabecalho } from '../components/Cabecalho';
import type { PropsModo } from './tiposModo';

/**
 * A grade tem 12 colunas na largura cheia e reflui para 6 e 2 em telas
 * menores. Os pontos de quebra são de container, não de janela: o painel vive
 * dentro de um `max-w-6xl`, então perguntar pela janela daria a resposta
 * errada num monitor largo.
 */
const PONTOS_QUEBRA = { lg: 900, md: 600, sm: 0 };
const COLUNAS = { lg: 12, md: 6, sm: 2 };
const ALTURA_LINHA = 44;

/**
 * Largura útil do container, medida de verdade.
 *
 * O `useContainerWidth` que a v2 do react-grid-layout oferece ficava preso na
 * largura inicial de fábrica (1280) neste layout, o que fazia a grade montar
 * blocos de 400px dentro de uma tela de 375 — sem reflow nenhum no celular.
 * Um ResizeObserver próprio resolve e não custa quase nada.
 */
function useLarguraContainer() {
  const ref = useRef<HTMLDivElement>(null);
  const [largura, setLargura] = useState(0);

  useEffect(() => {
    const alvo = ref.current;
    if (!alvo) return;

    const medir = () => setLargura(alvo.clientWidth);
    medir();

    // Dois gatilhos de propósito. O observer pega mudanças que não passam
    // pela janela (abrir a barra de edição, zoom do navegador); o evento de
    // resize cobre o caso comum e ambientes onde o observer não dispara.
    const observador = new ResizeObserver(medir);
    observador.observe(alvo);
    window.addEventListener('resize', medir);

    return () => {
      observador.disconnect();
      window.removeEventListener('resize', medir);
    };
  }, []);

  return { ref, largura };
}

/**
 * Modo "painel": os mesmos dados do mês em blocos que a usuária arruma.
 *
 * O layout é carregado em três degraus — servidor, cópia local, padrão de
 * fábrica —, nesta ordem: o servidor é a verdade entre aparelhos, a cópia
 * local cobre o intervalo até ele responder (e a rede caída), e o padrão
 * garante que uma conta nova abra numa tela montada, não vazia.
 */
export function ModoEstatico(props: PropsModo) {
  const { resumo, mesAtual, erro, setErro } = props;

  const [layout, setLayout] = useState<ItemLayout[]>(
    () => layoutLocal.ler() ?? LAYOUT_PADRAO,
  );
  const [editando, setEditando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState('');
  const { ref: containerRef, largura } = useLarguraContainer();

  /**
   * Arrumar blocos só faz sentido na tela larga: é lá que existem as 12
   * colunas que o layout descreve. Em tela estreita a grade vira uma pilha —
   * arrastar não teria para onde mover nada, e o resultado não é persistido.
   */
  const ehLarga = largura >= PONTOS_QUEBRA.lg;

  // Busca o layout do servidor uma vez. Não sobrescreve o que estiver na tela
  // se o servidor não tiver nada guardado — a cópia local é mais informativa
  // que o padrão de fábrica nesse caso.
  useEffect(() => {
    let valido = true;
    api
      .layoutDashboard()
      .then(({ layout: bruto }) => {
        const doServidor = interpretar(bruto);
        if (valido && doServidor) setLayout(doServidor);
      })
      .catch(() => {
        // Sem layout do servidor a tela continua utilizável com a cópia local.
        // Falhar aqui não merece a barra de erro vermelha do mês.
      });
    return () => {
      valido = false;
    };
  }, []);

  const aoMudarLayout = useCallback(
    (novo: Layout) => {
      // Só o layout da tela larga é o "mestre" — os menores o RGL deriva
      // sozinho, comprimindo tudo em 2 colunas. Gravar o derivado destruiria
      // o arranjo de 12 colunas: bastava abrir o painel uma vez no celular
      // para perder, no servidor, a tela montada no PC.
      if (!ehLarga) return;

      const itens = novo.map(({ i, x, y, w, h }) => ({
        i: i as IdWidget,
        x,
        y,
        w,
        h,
      }));
      setLayout(itens);
      layoutLocal.gravar(itens);
    },
    [ehLarga],
  );

  async function salvar() {
    setSalvando(true);
    setAviso('');
    try {
      await api.salvarLayoutDashboard(serializar(layout));
      setAviso('Layout salvo.');
      setEditando(false);
    } catch (e) {
      setErro(
        e instanceof Error ? e.message : 'Não foi possível salvar o layout.',
      );
    } finally {
      setSalvando(false);
    }
  }

  function restaurar() {
    setLayout(LAYOUT_PADRAO);
    layoutLocal.gravar(LAYOUT_PADRAO);
    setAviso('Layout restaurado. Salve para valer no servidor.');
  }

  function remover(id: IdWidget) {
    const novo = layout.filter((item) => item.i !== id);
    setLayout(novo);
    layoutLocal.gravar(novo);
  }

  function acrescentar(id: IdWidget) {
    const novo = adicionar(layout, id);
    setLayout(novo);
    layoutLocal.gravar(novo);
  }

  const mesResumo = resumo?.meses[mesAtual - 1];
  const disponiveis = widgetsDisponiveis(layout);

  return (
    <div className="min-h-screen bg-roxo-50 dark:bg-roxo-950">
      <Cabecalho
        tema={props.tema}
        aoAlternarTema={props.alternar}
        anos={props.anos}
        anoAtual={props.anoAtual}
        aoTrocarAno={props.setAnoAtual}
        aoCriarAno={(ano) => props.comAnos(() => api.criarAno(ano), ano)}
        aoArquivarAno={(ano) => props.comAnos(() => api.arquivarAno(ano))}
        aoDesarquivarAno={(ano) => props.comAnos(() => api.desarquivarAno(ano))}
        mesAtual={mesAtual}
        aoTrocarMes={props.setMesAtual}
        modo={props.modo}
        aoDefinirModo={props.aoDefinirModo}
        aoSair={props.aoSair}
        acoes={
          !ehLarga ? null : editando ? (
            <>
              <button
                onClick={restaurar}
                className="rounded-lg border border-roxo-200 px-3 py-1.5 text-xs font-medium text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
              >
                Restaurar padrão
              </button>
              <button
                onClick={salvar}
                disabled={salvando}
                className="rounded-lg bg-roxo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-roxo-400 disabled:opacity-50 dark:bg-roxo-400 dark:hover:bg-roxo-300"
              >
                {salvando ? 'Salvando…' : 'Salvar layout'}
              </button>
            </>
          ) : (
            <button
              onClick={() => {
                setAviso('');
                setEditando(true);
              }}
              className="rounded-lg border border-roxo-200 px-3 py-1.5 text-xs font-medium text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
            >
              Editar layout
            </button>
          )
        }
      />

      <main className="mx-auto max-w-6xl px-6 py-6">
        {erro && (
          <p className="mb-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-200">
            {erro}
          </p>
        )}

        {aviso && (
          <p className="mb-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
            {aviso}
          </p>
        )}

        {editando && ehLarga && (
          <BarraEdicao
            disponiveis={disponiveis}
            aoAdicionar={acrescentar}
            aoSair={() => setEditando(false)}
          />
        )}

        {/* A medição é feita neste div, e não no <main>: `clientWidth` inclui
            o padding, e passar a largura com padding à grade faria os blocos
            vazarem para fora dela. */}
        <div ref={containerRef}>
          {resumo && mesResumo && largura > 0 && (
            <ResponsiveGridLayout
              width={largura}
              // Só o mestre: `md` e `sm` o RGL deriva deste, comprimindo.
              layouts={{ lg: layout }}
              breakpoints={PONTOS_QUEBRA}
              cols={COLUNAS}
              rowHeight={ALTURA_LINHA}
              margin={[20, 20]}
              onLayoutChange={aoMudarLayout}
              // Arrastar só no modo de edição: fora dele, a tela é para usar —
              // e os widgets têm botões e formulários dentro, que um arraste
              // acidental atrapalharia.
              dragConfig={{ enabled: editando && ehLarga, handle: '.puxador' }}
              resizeConfig={{ enabled: editando && ehLarga }}
            >
              {layout.map((item) => (
                <div key={item.i} className="relative">
                  {editando && ehLarga && (
                    <ControlesBloco
                      aoRemover={() => remover(item.i)}
                      nome={CATALOGO[item.i].nome}
                    />
                  )}
                  {CATALOGO[item.i].desenhar({
                    ...props,
                    resumo,
                    mesResumo,
                    arquivado: resumo.arquivado,
                  } satisfies ContextoWidget)}
                </div>
              ))}
            </ResponsiveGridLayout>
          )}
        </div>
      </main>
    </div>
  );
}

/** Faixa de edição: o que dá para acrescentar, e como sair do modo. */
function BarraEdicao({
  disponiveis,
  aoAdicionar,
  aoSair,
}: {
  disponiveis: IdWidget[];
  aoAdicionar: (id: IdWidget) => void;
  aoSair: () => void;
}) {
  return (
    <div className="mb-4 rounded-xl border border-dashed border-roxo-300 bg-white px-5 py-4 dark:border-roxo-600 dark:bg-roxo-900">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-roxo-400 dark:text-roxo-200">
          Adicionar bloco
        </span>

        {disponiveis.length === 0 ? (
          <span className="text-xs text-roxo-300">
            Todos os blocos já estão na tela.
          </span>
        ) : (
          disponiveis.map((id) => (
            <button
              key={id}
              onClick={() => aoAdicionar(id)}
              className="rounded-lg border border-roxo-200 px-2.5 py-1 text-xs text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
            >
              + {CATALOGO[id].nome}
            </button>
          ))
        )}

        <button
          onClick={aoSair}
          className="ml-auto text-xs text-roxo-400 underline-offset-2 hover:underline dark:text-roxo-200"
        >
          Sair da edição
        </button>
      </div>

      <p className="mt-2 text-xs text-roxo-300">
        Arraste pela faixa no topo de cada bloco; puxe o canto inferior direito
        para redimensionar. O arranjo fica salvo neste aparelho na hora —
        "Salvar layout" guarda no servidor, para valer em todos.
      </p>
    </div>
  );
}

/**
 * Faixa de arraste e botão de remover, sobrepostos ao bloco durante a edição.
 *
 * Ficam por cima em vez de dentro do card para que nenhum widget precise
 * saber que existe um modo de edição.
 */
function ControlesBloco({
  aoRemover,
  nome,
}: {
  aoRemover: () => void;
  nome: string;
}) {
  return (
    <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between rounded-t-xl bg-roxo-500/90 px-3 py-1 text-white dark:bg-roxo-400/90">
      <span className="puxador flex-1 cursor-move truncate text-xs font-medium">
        ⠿ {nome}
      </span>
      <button
        onClick={aoRemover}
        aria-label={`Remover ${nome}`}
        title={`Remover ${nome}`}
        className="ml-2 rounded px-1.5 text-xs hover:bg-white/20"
      >
        ✕
      </button>
    </div>
  );
}
