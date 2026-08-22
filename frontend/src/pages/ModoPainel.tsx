import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import {
  DndContext,
  PointerSensor,
  useDraggable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';

import { api } from '../lib/api';
import {
  adicionar,
  atualizarConfig,
  CELL_H,
  CELL_W,
  centroide,
  colide,
  interpretar,
  layoutLocal,
  LAYOUT_PADRAO,
  limitarRetangulo,
  NIVEIS_ZOOM,
  ORIGEM_COL,
  ORIGEM_LIN,
  remover,
  retanguloPx,
  serializar,
  TOTAL_COLS,
  TOTAL_ROWS,
  ZOOM_PADRAO,
  type ItemLayout,
} from '../lib/layoutDashboard';
import { CATALOGO, ID_WIDGETS, type ContextoWidget, type TipoWidget } from '../components/widgets/catalogo';
import { Cabecalho } from '../components/Cabecalho';
import type { PropsModo } from './tiposModo';

/** Abaixo disto, o modo de edição fica fora de escopo — só rolar continua funcionando (ADR-0008). */
const LARGURA_MINIMA_EDICAO = 768;
const MARGEM_VIRTUALIZACAO = 300; // px, para o widget não "piscar" ao entrar na tela

/**
 * Modo "painel": um canvas grande (não infinito de verdade — ver ADR-0009)
 * com rolagem nativa do navegador e zoom em degraus, no molde do Google
 * Sheets. A usuária arrasta, redimensiona, adiciona e remove widgets.
 *
 * Ao contrário do modo planilha, este componente sempre se desenha num
 * tema escuro — o `<div className="dark">` na raiz ativa as variantes
 * `dark:` que os containers reaproveitados (calendário, lançamentos,
 * wishlist etc.) já têm, independente do tema claro/escuro escolhido pela
 * usuária no resto do app.
 */
export function ModoPainel(props: PropsModo) {
  const { resumo, mesAtual, anoAtual, erro, setErro } = props;

  const [layout, setLayout] = useState<ItemLayout[]>(
    () => layoutLocal.ler() ?? LAYOUT_PADRAO,
  );
  const [editando, setEditando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [toast, setToast] = useState('');
  const [catalogoAberto, setCatalogoAberto] = useState(false);
  const [zoom, setZoom] = useState<number>(ZOOM_PADRAO);
  const [scrollPos, setScrollPos] = useState({ left: 0, top: 0 });

  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);
  const conteudoRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ w: 0, h: 0 });

  const larga = viewport.w >= LARGURA_MINIMA_EDICAO;

  // Mede a área visível (para virtualização, "Centralizar" e a checagem de tela larga).
  useEffect(() => {
    const alvo = scrollRef.current;
    if (!alvo) return;
    const medir = () => setViewport({ w: alvo.clientWidth, h: alvo.clientHeight });
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(alvo);
    window.addEventListener('resize', medir);
    return () => {
      observador.disconnect();
      window.removeEventListener('resize', medir);
    };
  }, []);

  // Carrega do servidor uma vez ao entrar no modo (ADR-0006, "Carregamento e persistência").
  useEffect(() => {
    let valido = true;
    api
      .layoutDashboard()
      .then(({ layout: bruto }) => {
        const doServidor = interpretar(bruto);
        if (valido && doServidor) {
          setLayout(doServidor);
          layoutLocal.gravar(doServidor);
        }
      })
      .catch(() => {
        // Sem layout do servidor a tela continua utilizável com a cópia
        // local ou o padrão de fábrica — não é motivo para a barra de erro.
      });
    return () => {
      valido = false;
    };
  }, []);

  useEffect(() => () => clearTimeout(toastTimer.current), []);

  function mudarLayout(novo: ItemLayout[]) {
    setLayout(novo);
    layoutLocal.gravar(novo);
  }

  function avisar(texto: string) {
    clearTimeout(toastTimer.current);
    setToast(texto);
    toastTimer.current = setTimeout(() => setToast(''), 3000);
  }

  async function salvar() {
    setSalvando(true);
    try {
      await api.salvarLayoutDashboard(serializar(layout));
      avisar('Layout salvo.');
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar o layout.');
    } finally {
      setSalvando(false);
    }
  }

  // Só reseta o estado local — não apaga o layout já salvo no servidor até
  // a usuária confirmar com um novo "Salvar layout" (spec, seção 2).
  function restaurarPadrao() {
    layoutLocal.limpar();
    setLayout(LAYOUT_PADRAO);
    avisar('Layout restaurado. Salve para valer em todos os aparelhos.');
  }

  function adicionarWidget(tipo: TipoWidget) {
    mudarLayout(adicionar(layout, tipo));
    setCatalogoAberto(false);
  }

  function removerWidget(id: string) {
    mudarLayout(remover(layout, id));
  }

  function mudarConfig(id: string, config: Record<string, unknown>) {
    mudarLayout(atualizarConfig(layout, id, config));
  }

  /** Rola até enquadrar o centro do conjunto de widgets — a referência de "onde eu estou" do canvas. */
  const centralizar = useCallback(() => {
    const alvo = scrollRef.current;
    if (!alvo) return;
    const centro = centroide(layout);
    const x = (centro.coluna + ORIGEM_COL) * CELL_W * zoom;
    const y = (centro.linha + ORIGEM_LIN) * CELL_H * zoom;
    alvo.scrollTo({ left: x - viewport.w / 2, top: y - viewport.h / 2 });
    setScrollPos({ left: alvo.scrollLeft, top: alvo.scrollTop });
  }, [layout, viewport, zoom]);

  // Centraliza uma vez, assim que o viewport é medido pela primeira vez.
  const centralizouUmaVez = useRef(false);
  useEffect(() => {
    if (centralizouUmaVez.current || viewport.w === 0) return;
    centralizouUmaVez.current = true;
    const alvo = scrollRef.current;
    if (!alvo) return;
    const centro = centroide(layout);
    alvo.scrollLeft = (centro.coluna + ORIGEM_COL) * CELL_W * zoom - viewport.w / 2;
    alvo.scrollTop = (centro.linha + ORIGEM_LIN) * CELL_H * zoom - viewport.h / 2;
    setScrollPos({ left: alvo.scrollLeft, top: alvo.scrollTop });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewport]);

  /**
   * Muda o degrau de zoom mantendo o ponto do canvas que está no centro da
   * tela — sem isso, cada clique no zoom "chutaria" a visão para outro
   * lugar, exatamente o tipo de desorientação que a barra de scroll (e o
   * zoom) deveriam resolver, não criar de novo.
   */
  function mudarZoom(novoZoom: number) {
    const alvo = scrollRef.current;
    const conteudo = conteudoRef.current;
    if (!alvo || !conteudo) {
      setZoom(novoZoom);
      return;
    }
    const centroXConteudo = (alvo.scrollLeft + viewport.w / 2) / zoom;
    const centroYConteudo = (alvo.scrollTop + viewport.h / 2) / zoom;

    // Aplica o novo zoom no DOM *antes* de mexer no scroll: só assim o
    // navegador conhece a área rolável nova (`scrollWidth`/`scrollHeight`)
    // na hora de aceitar o `scrollLeft`/`scrollTop` calculados — escrever
    // scroll contra o tamanho antigo (esperando o React re-renderizar
    // depois) faz o navegador arredondar para o limite antigo, menor.
    conteudo.style.transform = `scale(${novoZoom})`;
    const novoScrollLeft = centroXConteudo * novoZoom - viewport.w / 2;
    const novoScrollTop = centroYConteudo * novoZoom - viewport.h / 2;
    alvo.scrollLeft = novoScrollLeft;
    alvo.scrollTop = novoScrollTop;

    setZoom(novoZoom);
    setScrollPos({ left: alvo.scrollLeft, top: alvo.scrollTop });
  }

  const indiceZoom = NIVEIS_ZOOM.indexOf(zoom as (typeof NIVEIS_ZOOM)[number]);
  const aumentarZoom = () => indiceZoom < NIVEIS_ZOOM.length - 1 && mudarZoom(NIVEIS_ZOOM[indiceZoom + 1]);
  const diminuirZoom = () => indiceZoom > 0 && mudarZoom(NIVEIS_ZOOM[indiceZoom - 1]);

  const sensores = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  function aoSoltarArrasto(evento: DragEndEvent) {
    const item = layout.find((i) => i.id === evento.active.id);
    if (!item) return;
    const deltaCol = Math.round(evento.delta.x / zoom / CELL_W);
    const deltaLin = Math.round(evento.delta.y / zoom / CELL_H);
    if (deltaCol === 0 && deltaLin === 0) return;

    const candidato = limitarRetangulo({
      coluna: item.coluna + deltaCol,
      linha: item.linha + deltaLin,
      largura: item.largura,
      altura: item.altura,
    });
    if (colide(layout, candidato, item.id)) return; // volta pro lugar sozinho

    mudarLayout(
      layout.map((i) => (i.id === item.id ? { ...i, ...candidato } : i)),
    );
  }

  function aoRedimensionar(id: string, largura: number, altura: number) {
    const item = layout.find((i) => i.id === id);
    if (!item) return;
    // Redimensionar mantém o canto superior esquerdo fixo — quem cede é o
    // tamanho, não a posição (diferente do arrasto, onde é o oposto).
    const larguraMax = TOTAL_COLS - ORIGEM_COL - item.coluna;
    const alturaMax = TOTAL_ROWS - ORIGEM_LIN - item.linha;
    const larguraFinal = Math.max(1, Math.min(largura, larguraMax));
    const alturaFinal = Math.max(1, Math.min(altura, alturaMax));

    const candidato = { coluna: item.coluna, linha: item.linha, largura: larguraFinal, altura: alturaFinal };
    if (colide(layout, candidato, id)) return;
    mudarLayout(layout.map((i) => (i.id === id ? { ...i, ...candidato } : i)));
  }

  function aoRolar() {
    const alvo = scrollRef.current;
    if (alvo) setScrollPos({ left: alvo.scrollLeft, top: alvo.scrollTop });
  }

  // Virtualização: só monta o que intersecta a janela visível (mais margem).
  const visiveis = useMemo(() => {
    if (viewport.w === 0) return layout;
    const retVisivel = {
      left: (scrollPos.left - MARGEM_VIRTUALIZACAO) / zoom,
      top: (scrollPos.top - MARGEM_VIRTUALIZACAO) / zoom,
      right: (scrollPos.left + viewport.w + MARGEM_VIRTUALIZACAO) / zoom,
      bottom: (scrollPos.top + viewport.h + MARGEM_VIRTUALIZACAO) / zoom,
    };
    return layout.filter((item) => {
      const r = retanguloPx(item);
      return (
        r.left < retVisivel.right &&
        r.left + r.width > retVisivel.left &&
        r.top < retVisivel.bottom &&
        r.top + r.height > retVisivel.top
      );
    });
  }, [layout, scrollPos, viewport, zoom]);

  const mesResumo = resumo?.meses[mesAtual - 1];
  const podeEditar = editando && larga;

  return (
    <div className="dark min-h-screen bg-roxo-950">
      <Cabecalho
        tema={props.tema}
        aoAlternarTema={props.alternar}
        anos={props.anos}
        anoAtual={anoAtual}
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
          !larga ? null : podeEditar ? (
            <>
              <button
                onClick={() => setCatalogoAberto((v) => !v)}
                className="rounded-lg border border-white/20 px-3 py-1.5 text-xs font-medium text-white/80 hover:bg-white/10"
              >
                + Adicionar
              </button>
              <button
                onClick={restaurarPadrao}
                className="rounded-lg border border-white/20 px-3 py-1.5 text-xs font-medium text-white/80 hover:bg-white/10"
              >
                Restaurar padrão
              </button>
              <button
                onClick={salvar}
                disabled={salvando}
                className="rounded-lg bg-fuchsia-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-fuchsia-400 disabled:opacity-50"
              >
                {salvando ? 'Salvando…' : 'Salvar layout'}
              </button>
              <button
                onClick={() => {
                  setEditando(false);
                  setCatalogoAberto(false);
                }}
                className="rounded-lg border border-white/20 px-3 py-1.5 text-xs font-medium text-white/80 hover:bg-white/10"
              >
                Concluir
              </button>
            </>
          ) : (
            <button
              onClick={() => setEditando(true)}
              className="rounded-lg border border-white/20 px-3 py-1.5 text-xs font-medium text-white/80 hover:bg-white/10"
            >
              Editar layout
            </button>
          )
        }
      />

      {erro && (
        <p className="mx-6 mt-4 rounded-lg bg-rose-950 px-4 py-3 text-sm text-rose-200">
          {erro}
        </p>
      )}

      <div className="relative h-[calc(100vh-73px)]">
        {toast && (
          <div className="pointer-events-none absolute right-4 top-4 z-30 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-medium text-white shadow-lg">
            {toast}
          </div>
        )}

        {podeEditar && catalogoAberto && (
          <CatalogoWidgets aoEscolher={adicionarWidget} aoFechar={() => setCatalogoAberto(false)} />
        )}

        {/* Zoom e "Centralizar", no molde do canto inferior direito do Google Sheets. */}
        <div className="absolute bottom-4 right-4 z-20 flex items-center gap-1 rounded-full border border-white/20 bg-roxo-900 px-1 py-1 shadow-lg">
          <button
            onClick={centralizar}
            title="Centralizar"
            aria-label="Centralizar"
            className="flex h-8 w-8 items-center justify-center rounded-full text-white/80 hover:bg-white/10"
          >
            ◎
          </button>
          <div className="mx-1 h-5 w-px bg-white/15" />
          <button
            onClick={diminuirZoom}
            disabled={indiceZoom <= 0}
            aria-label="Diminuir zoom"
            className="flex h-8 w-8 items-center justify-center rounded-full text-white/80 hover:bg-white/10 disabled:opacity-30"
          >
            −
          </button>
          <button
            onClick={() => mudarZoom(ZOOM_PADRAO)}
            className="w-12 rounded-full py-1 text-center text-xs text-white/70 hover:bg-white/10"
            title="Redefinir zoom"
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            onClick={aumentarZoom}
            disabled={indiceZoom >= NIVEIS_ZOOM.length - 1}
            aria-label="Aumentar zoom"
            className="flex h-8 w-8 items-center justify-center rounded-full text-white/80 hover:bg-white/10 disabled:opacity-30"
          >
            +
          </button>
        </div>

        <DndContext sensors={sensores} onDragEnd={aoSoltarArrasto}>
          {/* Área rolável de verdade: barra de scroll nativa, e é o
              `scrollLeft`/`scrollTop` dela que ancora o zoom (ADR-0009). */}
          <div ref={scrollRef} onScroll={aoRolar} className="h-full w-full overflow-auto">
            <div
              ref={conteudoRef}
              className="relative"
              style={{
                width: TOTAL_COLS * CELL_W,
                height: TOTAL_ROWS * CELL_H,
                transform: `scale(${zoom})`,
                transformOrigin: '0 0',
                backgroundImage:
                  'linear-gradient(to right, rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.06) 1px, transparent 1px)',
                backgroundSize: `${CELL_W}px ${CELL_H}px`,
              }}
            >
              {resumo &&
                mesResumo &&
                visiveis.map((item) => (
                  <WidgetNoCanvas
                    key={item.id}
                    item={item}
                    zoom={zoom}
                    editando={podeEditar}
                    aoRemover={() => removerWidget(item.id)}
                    aoRedimensionar={(w, h) => aoRedimensionar(item.id, w, h)}
                  >
                    {CATALOGO[item.tipo].desenhar({
                      ...props,
                      resumo,
                      mesResumo,
                      arquivado: resumo.arquivado,
                      item,
                      aoMudarConfig: (config) => mudarConfig(item.id, config),
                    } satisfies ContextoWidget)}
                  </WidgetNoCanvas>
                ))}
            </div>
          </div>
        </DndContext>
      </div>
    </div>
  );
}

/** Um widget posicionado no canvas: moldura de arrasto/remoção + o conteúdo do catálogo. */
function WidgetNoCanvas({
  item,
  zoom,
  editando,
  aoRemover,
  aoRedimensionar,
  children,
}: {
  item: ItemLayout;
  zoom: number;
  editando: boolean;
  aoRemover: () => void;
  aoRedimensionar: (largura: number, altura: number) => void;
  children: ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: item.id,
    disabled: !editando,
  });
  const r = retanguloPx(item);
  const nome = CATALOGO[item.tipo].nome;

  return (
    <div
      ref={setNodeRef}
      className="absolute"
      style={{
        left: r.left,
        top: r.top,
        width: r.width,
        height: r.height,
        // O delta do dnd-kit vem em pixels de tela — dividir pelo zoom
        // devolve ao espaço não-escalado do widget (que já mora dentro do
        // wrapper com `transform: scale(zoom)`), senão o widget "correria"
        // mais rápido que o cursor num zoom diferente de 100%.
        transform: transform
          ? `translate(${transform.x / zoom}px, ${transform.y / zoom}px)`
          : undefined,
        zIndex: isDragging ? 20 : 1,
        transition: isDragging ? undefined : 'left 120ms ease, top 120ms ease',
      }}
    >
      <div className="relative h-full w-full">
        {editando && (
          <div
            {...listeners}
            {...attributes}
            className="touch-none absolute inset-x-0 top-0 z-10 flex cursor-move items-center justify-between rounded-t-2xl bg-black/40 px-3 py-1 text-white backdrop-blur-sm"
          >
            <span className="truncate text-xs font-medium">⠿ {nome}</span>
            <button
              onPointerDown={(e) => e.stopPropagation()}
              onClick={aoRemover}
              aria-label={`Remover ${nome}`}
              title={`Remover ${nome}`}
              className="ml-2 rounded px-1.5 text-xs hover:bg-white/20"
            >
              ✕
            </button>
          </div>
        )}
        {children}
        {editando && (
          <AlcaRedimensionar
            largura={item.largura}
            altura={item.altura}
            zoom={zoom}
            aoConcluir={aoRedimensionar}
          />
        )}
      </div>
    </div>
  );
}

/** Alça de redimensionar no canto inferior direito: gesto próprio, sem depender de biblioteca de grade (ADR-0008). */
function AlcaRedimensionar({
  largura,
  altura,
  zoom,
  aoConcluir,
}: {
  largura: number;
  altura: number;
  zoom: number;
  aoConcluir: (largura: number, altura: number) => void;
}) {
  function aoIniciar(e: ReactPointerEvent) {
    e.stopPropagation();
    e.preventDefault();
    const inicioX = e.clientX;
    const inicioY = e.clientY;
    const preview = { largura, altura };

    function mover(ev: PointerEvent) {
      const deltaCol = Math.round((ev.clientX - inicioX) / zoom / CELL_W);
      const deltaLin = Math.round((ev.clientY - inicioY) / zoom / CELL_H);
      preview.largura = Math.max(1, largura + deltaCol);
      preview.altura = Math.max(1, altura + deltaLin);
    }

    function soltar() {
      window.removeEventListener('pointermove', mover);
      window.removeEventListener('pointerup', soltar);
      aoConcluir(preview.largura, preview.altura);
    }
    window.addEventListener('pointermove', mover);
    window.addEventListener('pointerup', soltar);
  }

  return (
    <div
      onPointerDown={aoIniciar}
      className="touch-none absolute bottom-1 right-1 z-10 h-4 w-4 cursor-se-resize rounded-sm border-b-2 border-r-2 border-white/50"
    />
  );
}

/** Menu flutuante para adicionar um widget do catálogo. Tipos podem repetir (ADR-0008). */
function CatalogoWidgets({
  aoEscolher,
  aoFechar,
}: {
  aoEscolher: (tipo: TipoWidget) => void;
  aoFechar: () => void;
}) {
  return (
    <div className="absolute left-4 top-4 z-30 max-h-[70vh] w-64 overflow-auto rounded-xl border border-white/10 bg-roxo-900 p-2 shadow-xl">
      <div className="mb-1 flex items-center justify-between px-2 py-1">
        <span className="text-xs font-medium uppercase tracking-wide text-white/50">
          Adicionar widget
        </span>
        <button onClick={aoFechar} className="text-white/40 hover:text-white">
          ✕
        </button>
      </div>
      <ul>
        {ID_WIDGETS.map((tipo) => (
          <li key={tipo}>
            <button
              onClick={() => aoEscolher(tipo)}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-white/80 hover:bg-white/10"
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-sm bg-gradient-to-br from-fuchsia-400 to-cyan-400"
                aria-hidden
              />
              {CATALOGO[tipo].nome}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
