/**
 * Catálogo de widgets do modo painel (ADR-0007, ADR-0008).
 *
 * Cada entrada diz como um tipo se chama no menu "+", que tamanho nasce e o
 * que desenha. O canvas, a persistência e o menu leem só esta lista —
 * nenhum deles sabe o que existe dentro de um widget. Um mesmo tipo pode
 * ter várias instâncias no canvas ao mesmo tempo (ex.: duas contas
 * diferentes no mesmo tipo "Contas"), cada uma com seu próprio `config`.
 *
 * Três blocos da imagem de referência ficam de fora do catálogo v1 —
 * "Dívidas" (cartão e tabela) e "Resumo do plano de contas" — porque
 * dependem de orçamento/dívida como conceito que o sistema ainda não tem
 * (ADR-0007). Não aparecem aqui de propósito: nada no menu "+" oferece o
 * que ainda não existe.
 */

import type { ReactNode } from 'react';
import { api } from '../../lib/api';
import { moeda, NOMES_MESES } from '../../lib/formato';
import type { ItemLayout } from '../../lib/layoutDashboard';
import { CalendarioVencimentos } from '../CalendarioVencimentos';
import { GastosFixos } from '../GastosFixos';
import { GastosPorCategoria } from '../GastosPorCategoria';
import { TabelaLancamentos } from '../TabelaLancamentos';
import { Wishlist } from '../Wishlist';
import { CabecalhoPeriodo } from '../widgets-painel/CabecalhoPeriodo';
import { DetalhamentoDespesas } from '../widgets-painel/DetalhamentoDespesas';
import { InvestimentosTabela } from '../widgets-painel/InvestimentosTabela';
import { LembreteDia } from '../widgets-painel/LembreteDia';
import { StatCard } from '../widgets-painel/StatCard';
import { TodasContas } from '../widgets-painel/TodasContas';
import { DespesasDiarias } from './DespesasDiarias';
import { FaturaCartao } from './FaturaCartao';
import { GraficoCategorias } from './GraficoCategorias';
import { SaldoInicial } from './SaldoInicial';
import type { PropsModo } from '../../pages/tiposModo';
import type { ResumoAno, ResumoMes } from '../../types/api';

/** O que um widget recebe para se desenhar: os dados do mês, as ações e a própria instância. */
export interface ContextoWidget extends PropsModo {
  /** Já resolvidos por `ModoPainel` — todo widget precisa dos dois. */
  resumo: ResumoAno;
  mesResumo: ResumoMes;
  arquivado: boolean;
  item: ItemLayout;
  aoMudarConfig: (config: Record<string, unknown>) => void;
}

interface DefinicaoWidget {
  /** Nome no menu de adicionar. Não é o título do card — esse vem do próprio. */
  nome: string;
  /** Tamanho com que a instância nasce, em unidades de célula (ADR-0008). */
  tamanho: { w: number; h: number };
  desenhar: (ctx: ContextoWidget) => ReactNode;
}

export const CATALOGO = {
  'cabecalho-periodo': {
    nome: 'Cabeçalho do período',
    tamanho: { w: 12, h: 1 },
    desenhar: (c) => <CabecalhoPeriodo ano={c.anoAtual} mes={c.mesAtual} />,
  },

  'saldo-atual': {
    nome: 'Saldo atual',
    tamanho: { w: 4, h: 2 },
    desenhar: (c) => (
      <StatCard
        rotulo="Saldo do mês"
        valor={c.mesResumo.saldo}
        negativo={Number(c.mesResumo.saldo) < 0}
        acento="violeta"
      />
    ),
  },

  'todas-contas': {
    nome: 'Todas as contas',
    tamanho: { w: 4, h: 2 },
    desenhar: (c) => {
      const contaId = (c.item.config?.contaId as number | undefined) ?? null;
      return (
        <TodasContas
          porConta={c.mesResumo.por_conta}
          saldoTotal={c.mesResumo.saldo}
          contaId={contaId}
          aoMudarConta={(novo) => c.aoMudarConfig({ ...c.item.config, contaId: novo })}
        />
      );
    },
  },

  'lembrete-dia': {
    nome: 'Lembrete do dia',
    tamanho: { w: 4, h: 2 },
    desenhar: (c) => (
      <LembreteDia
        gastosFixos={c.gastosFixos}
        cartoes={c.contas.filter((conta) => conta.tipo === 'cartao_credito')}
        faturas={c.faturas}
        ano={c.anoAtual}
        mes={c.mesAtual}
      />
    ),
  },

  receita: {
    nome: 'Receita',
    tamanho: { w: 3, h: 2 },
    desenhar: (c) => (
      <StatCard rotulo="Receita" valor={c.mesResumo.entradas} acento="ciano" />
    ),
  },

  'despesas-contas': {
    nome: 'Despesas & contas',
    tamanho: { w: 3, h: 2 },
    desenhar: (c) => {
      const pendentes = c.gastosFixos
        .filter((g) => g.ativo && !g.meses.some((m) => m.mes === c.mesAtual && m.situacao === 'pago'))
        .reduce((s, g) => s + Number(g.valor), 0);
      return (
        <StatCard
          rotulo="Despesas & contas"
          valor={Number(c.mesResumo.saidas) + pendentes}
          legenda={`${moeda(c.mesResumo.saidas)} já saído + ${moeda(pendentes)} a pagar`}
          acento="rosa"
        />
      );
    },
  },

  'investimentos-cartao': {
    nome: 'Investimentos',
    tamanho: { w: 3, h: 2 },
    desenhar: (c) => (
      <StatCard
        rotulo="Guardado no mês"
        valor={c.mesResumo.guardado_no_mes}
        legenda={`Acumulado: ${moeda(c.mesResumo.guardado_acumulado)}`}
        acento="ambar"
      />
    ),
  },

  'fatura-cartao': {
    nome: 'Fatura do cartão',
    tamanho: { w: 3, h: 2 },
    desenhar: (c) => (
      <FaturaCartao
        contas={c.contas}
        posicaoCartoes={c.mesResumo.por_cartao}
        faturas={c.faturas}
      />
    ),
  },

  patrimonio: {
    nome: 'Patrimônio líquido total',
    tamanho: { w: 4, h: 4 },
    desenhar: (c) => {
      const total = c.mesResumo.por_conta.reduce(
        (s, conta) => s + Number(conta.saldo) + Number(conta.guardado),
        0,
      );
      return (
        <StatCard
          rotulo="Patrimônio líquido"
          valor={total}
          legenda="Saldo + guardado, contas correntes"
          acento="violeta"
          filho={
            <ul className="mt-3 space-y-1 border-t border-white/10 pt-3">
              {c.mesResumo.por_conta.map((conta) => (
                <li key={conta.conta_id} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-white/60">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: conta.cor }}
                    />
                    {conta.nome}
                  </span>
                  <span className="tabular-nums text-white/80">
                    {moeda(Number(conta.saldo) + Number(conta.guardado))}
                  </span>
                </li>
              ))}
            </ul>
          }
        />
      );
    },
  },

  'despesas-diarias': {
    nome: 'Despesas diárias',
    tamanho: { w: 6, h: 3 },
    desenhar: (c) => (
      <DespesasDiarias lancamentos={c.lancamentos} ano={c.anoAtual} mes={c.mesAtual} />
    ),
  },

  'gastos-rosca': {
    nome: 'Para onde meu dinheiro vai',
    tamanho: { w: 4, h: 4 },
    desenhar: (c) => <GraficoCategorias mes={c.mesResumo} categorias={c.categorias} />,
  },

  'detalhamento-despesas': {
    nome: 'Detalhamento das despesas',
    tamanho: { w: 4, h: 4 },
    desenhar: (c) => {
      const agruparPor = (c.item.config?.agruparPor as 'categoria' | 'conta' | undefined) ?? 'categoria';
      return (
        <DetalhamentoDespesas
          mes={c.mesResumo}
          categorias={c.categorias}
          contas={c.contas}
          lancamentos={c.lancamentos}
          agruparPor={agruparPor}
          aoMudarAgrupamento={(novo) => c.aoMudarConfig({ ...c.item.config, agruparPor: novo })}
        />
      );
    },
  },

  calendario: {
    nome: 'Calendário de vencimentos',
    tamanho: { w: 6, h: 5 },
    desenhar: (c) => (
      <CalendarioVencimentos
        preencher
        gastos={c.gastosFixos}
        cartoes={c.contas.filter((conta) => conta.tipo === 'cartao_credito')}
        faturas={c.faturas}
        ano={c.anoAtual}
        mes={c.mesAtual}
        somenteLeitura={c.arquivado}
        aoAlternar={c.alternarGastoFixo}
        aoAlternarFatura={async (cartao, pago) => {
          try {
            if (pago) {
              await api.pagarFatura(
                c.anoAtual,
                cartao.id,
                c.mesAtual,
                cartao.conta_pagamento_padrao_id,
              );
            } else {
              await api.desfazerFatura(c.anoAtual, cartao.id, c.mesAtual);
            }
            await c.recarregar();
          } catch (e) {
            c.setErro(
              e instanceof Error ? e.message : 'Não foi possível atualizar a fatura.',
            );
          }
        }}
      />
    ),
  },

  'saldo-inicial': {
    nome: 'Saldo inicial',
    tamanho: { w: 4, h: 3 },
    desenhar: (c) => <SaldoInicial mes={c.mesResumo} />,
  },

  'despesas-tabela': {
    nome: 'Despesas por categoria (tabela)',
    tamanho: { w: 6, h: 5 },
    desenhar: (c) => (
      <GastosPorCategoria preencher mes={c.mesResumo} categorias={c.categorias} />
    ),
  },

  'contas-recorrentes': {
    nome: 'Contas recorrentes',
    tamanho: { w: 6, h: 5 },
    desenhar: (c) => (
      <GastosFixos
        preencher
        gastos={c.gastosFixos}
        contas={c.contas}
        mes={c.mesAtual}
        somenteLeitura={c.arquivado}
        aoCriar={c.acao(api.criarGastoFixo)}
        aoAtualizar={c.acao(api.atualizarGastoFixo)}
        aoAlternar={c.alternarGastoFixo}
        aoExcluir={c.acao(api.excluirGastoFixo)}
      />
    ),
  },

  'investimentos-tabela': {
    nome: 'Investimentos (tabela)',
    tamanho: { w: 6, h: 3 },
    desenhar: (c) => <InvestimentosTabela porConta={c.mesResumo.por_conta} />,
  },

  lancamentos: {
    nome: 'Lançamentos do mês',
    tamanho: { w: 12, h: 5 },
    desenhar: (c) => (
      <TabelaLancamentos
        preencher
        titulo={NOMES_MESES[c.mesAtual - 1]}
        lancamentos={c.lancamentos}
        contas={c.contas}
        somenteLeitura={c.arquivado}
        aoEditar={c.setEditandoLancamento}
        aoExcluir={c.acao(api.excluirLancamento)}
      />
    ),
  },

  wishlist: {
    nome: 'Wishlist',
    tamanho: { w: 4, h: 4 },
    desenhar: (c) => (
      <Wishlist
        preencher
        desejos={c.desejos}
        totalGuardado={c.resumo.total_guardado}
        somenteLeitura={c.arquivado}
        aoCriar={c.acao(api.criarDesejo)}
        aoAtualizar={c.acao(api.atualizarDesejo)}
        aoExcluir={c.acao(api.excluirDesejo)}
      />
    ),
  },
} satisfies Record<string, DefinicaoWidget>;

export type TipoWidget = keyof typeof CATALOGO;

/** Tipos na ordem em que aparecem no menu de adicionar. */
export const ID_WIDGETS = Object.keys(CATALOGO) as TipoWidget[];

export const TAMANHO_PADRAO: Record<TipoWidget, { w: number; h: number }> =
  Object.fromEntries(
    ID_WIDGETS.map((id) => [id, CATALOGO[id].tamanho]),
  ) as Record<TipoWidget, { w: number; h: number }>;

