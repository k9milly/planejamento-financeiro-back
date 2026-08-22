import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type WheelEvent as ReactWheelEvent,
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
  LIMITE_PX,
  remover,
  retanguloPx,
  serializar,
  type ItemLayout,
} from '../lib/layoutDashboard';
import { CATALOGO, ID_WIDGETS, type ContextoWidget, type TipoWidget } from '../components/widgets/catalogo';
import { Cabecalho } from '../components/Cabecalho';
import type { PropsModo } from './tiposModo';

/** Abaixo disto, o modo de edição fica fora de escopo — só o pan por toque funciona (ADR-0008). */
const LARGURA_MINIMA_EDICAO = 768;
const MARGEM_VIRTUALIZACAO = 300; // px, para o widget não "piscar" ao entrar na tela

/**
 * Modo "painel": canvas infinito, pannable nas quatro direções, onde a
 * usuária arrasta, redimensiona, adiciona e remove widgets (ADR-0008).
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
  const [pan, setPan] = useState({ x: window.innerWidth / 2, y: 80 });

  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ w: 0, h: 0 });

  const larga = viewport.w >= LARGURA_MINIMA_EDICAO;

  // Mede o viewport para virtualização e para o botão "Centralizar".
  useEffect(() => {
    const alvo = viewportRef.current;
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

  // Carrega do servidor uma vez ao entrar no modo (ADR-0006/ADR-0008, "Carregamento e persistência").
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

  async function salvar() {
    setSalvando(true);
    try {
      await api.salvarLayoutDashboard(serializar(layout));
      clearTimeout(toastTimer.current);
      setToast('Layout salvo.');
      toastTimer.current = setTimeout(() => setToast(''), 3000);
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
    clearTimeout(toastTimer.current);
    setToast('Layout restaurado. Salve para valer em todos os aparelhos.');
    toastTimer.current = setTimeout(() => setToast(''), 3000);
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

  const centralizar = useCallback(() => {
    const centro = centroide(layout);
    setPan({
      x: viewport.w / 2 - (centro.coluna * CELL_W + CELL_W / 2),
      y: viewport.h / 2 - (centro.linha * CELL_H + CELL_H / 2),
    });
  }, [layout, viewport]);

  // Centraliza uma vez, assim que o viewport é medido pela primeira vez.
  const centralizouUmaVez = useRef(false);
  useEffect(() => {
    if (centralizouUmaVez.current || viewport.w === 0) return;
    centralizouUmaVez.current = true;
    centralizar();
  }, [viewport, centralizar]);

  const arrastarBg = usePanDoFundo(pan, setPan);

  const sensores = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  function aoSoltarArrasto(evento: DragEndEvent) {
    const item = layout.find((i) => i.id === evento.active.id);
    if (!item) return;
    const deltaCol = Math.round(evento.delta.x / CELL_W);
    const deltaLin = Math.round(evento.delta.y / CELL_H);
    if (deltaCol === 0 && deltaLin === 0) return;

    const candidato = {
      coluna: item.coluna + deltaCol,
      linha: item.linha + deltaLin,
      largura: item.largura,
      altura: item.altura,
    };
    if (colide(layout, candidato, item.id)) return; // volta pro lugar sozinho

    mudarLayout(
      layout.map((i) => (i.id === item.id ? { ...i, ...candidato } : i)),
    );
  }

  function aoRedimensionar(id: string, largura: number, altura: number) {
    const item = layout.find((i) => i.id === id);
    if (!item) return;
    const candidato = { coluna: item.coluna, linha: item.linha, largura, altura };
    if (largura < 1 || altura < 1) return;
    if (colide(layout, candidato, id)) return;
    mudarLayout(layout.map((i) => (i.id === id ? { ...i, largura, altura } : i)));
  }

  // Virtualização: só monta o que intersecta a janela visível (mais margem).
  const visiveis = useMemo(() => {
    if (viewport.w === 0) return layout;
    const retVisivel = {
      left: -pan.x - MARGEM_VIRTUALIZACAO,
      top: -pan.y - MARGEM_VIRTUALIZACAO,
      right: -pan.x + viewport.w + MARGEM_VIRTUALIZACAO,
      bottom: -pan.y + viewport.h + MARGEM_VIRTUALIZACAO,
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
  }, [layout, pan, viewport]);

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

      <div className="relative h-[calc(100vh-73px)] overflow-hidden">
        {toast && (
          <div className="absolute right-4 top-4 z-30 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-medium text-white shadow-lg">
            {toast}
          </div>
        )}

        {podeEditar && catalogoAberto && (
          <CatalogoWidgets aoEscolher={adicionarWidget} aoFechar={() => setCatalogoAberto(false)} />
        )}

        <button
          onClick={centralizar}
          title="Centralizar"
          aria-label="Centralizar"
          className="absolute bottom-4 right-4 z-20 flex h-10 w-10 items-center justify-center rounded-full border border-white/20 bg-roxo-900 text-white/80 shadow-lg hover:bg-roxo-800"
        >
          ◎
        </button>

        <DndContext sensors={sensores} onDragEnd={aoSoltarArrasto}>
          {/* Janela de visualização: recorta o canvas, mas não limita até
              onde ele existe — arrastar o fundo continua livre além disso
              (ver ADR-0008, "sobre 'sem overflow: hidden'"). */}
          <div
            ref={viewportRef}
            className="h-full w-full touch-none"
            style={{
              backgroundImage:
                'linear-gradient(to right, rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.06) 1px, transparent 1px)',
              backgroundSize: `${CELL_W}px ${CELL_H}px`,
              backgroundPosition: `${pan.x}px ${pan.y}px`,
            }}
            {...arrastarBg}
          >
            <div
              className="relative"
              style={{ transform: `translate(${pan.x}px, ${pan.y}px)` }}
            >
              {resumo &&
                mesResumo &&
                visiveis.map((item) => (
                  <WidgetNoCanvas
                    key={item.id}
                    item={item}
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
  editando,
  aoRemover,
  aoRedimensionar,
  children,
}: {
  item: ItemLayout;
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
        transform: transform ? `translate(${transform.x}px, ${transform.y}px)` : undefined,
        zIndex: isDragging ? 20 : 1,
        transition: isDragging ? undefined : 'left 120ms ease, top 120ms ease',
      }}
    >
      <div className="relative h-full w-full">
        {editando && (
          <div
            {...listeners}
            {...attributes}
            className="absolute inset-x-0 top-0 z-10 flex cursor-move items-center justify-between rounded-t-2xl bg-black/40 px-3 py-1 text-white backdrop-blur-sm"
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
  aoConcluir,
}: {
  largura: number;
  altura: number;
  aoConcluir: (largura: number, altura: number) => void;
}) {
  function aoIniciar(e: ReactPointerEvent) {
    e.stopPropagation();
    e.preventDefault();
    const inicioX = e.clientX;
    const inicioY = e.clientY;

    function mover(ev: PointerEvent) {
      const deltaCol = Math.round((ev.clientX - inicioX) / CELL_W);
      const deltaLin = Math.round((ev.clientY - inicioY) / CELL_H);
      preview.largura = Math.max(1, largura + deltaCol);
      preview.altura = Math.max(1, altura + deltaLin);
    }

    const preview = { largura, altura };
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
      className="absolute bottom-1 right-1 z-10 h-4 w-4 cursor-se-resize rounded-sm border-b-2 border-r-2 border-white/50"
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

/** Arrastar o fundo (fora de qualquer widget) move o pan — sem scroll nativo (ADR-0008). */
function usePanDoFundo(
  pan: { x: number; y: number },
  setPan: (p: { x: number; y: number }) => void,
) {
  const arrastando = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  function limitar(v: number) {
    return Math.max(-LIMITE_PX, Math.min(LIMITE_PX, v));
  }

  function onPointerDown(e: ReactPointerEvent) {
    if (e.target !== e.currentTarget) return; // só o fundo, não um widget
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    arrastando.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
  }

  function onPointerMove(e: ReactPointerEvent) {
    if (!arrastando.current) return;
    const a = arrastando.current;
    setPan({
      x: limitar(a.panX + (e.clientX - a.x)),
      y: limitar(a.panY + (e.clientY - a.y)),
    });
  }

  function onPointerUp() {
    arrastando.current = null;
  }

  function onWheel(e: ReactWheelEvent) {
    setPan({ x: limitar(pan.x - e.deltaX), y: limitar(pan.y - e.deltaY) });
  }

  return { onPointerDown, onPointerMove, onPointerUp, onWheel };
}
