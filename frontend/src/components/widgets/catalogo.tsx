/**
 * Catálogo de widgets do modo painel (ADR-0007).
 *
 * Cada entrada diz como um bloco se chama no menu "+", que tamanho ele nasce
 * e o que ele desenha. Adicionar um bloco novo à interface é acrescentar uma
 * entrada aqui — o motor de grade, a persistência e o menu leem esta lista, e
 * nenhum deles precisa saber o que existe dentro de um widget.
 *
 * Quase todo widget reaproveita um container que o modo planilha já usa: os
 * dois modos mostram o mesmo mês, então duplicar a lógica de exibição só
 * criaria duas verdades para o mesmo número.
 */

import type { ReactNode } from 'react';
import { api } from '../../lib/api';
import { NOMES_MESES } from '../../lib/formato';
import { CalendarioVencimentos } from '../CalendarioVencimentos';
import { GastosFixos } from '../GastosFixos';
import { GastosPorCategoria } from '../GastosPorCategoria';
import { TabelaLancamentos } from '../TabelaLancamentos';
import { TotaisMes } from '../TotaisMes';
import { TotalGuardado } from '../TotalGuardado';
import { Wishlist } from '../Wishlist';
import { DespesasDiarias } from './DespesasDiarias';
import { FaturaCartao } from './FaturaCartao';
import { GraficoCategorias } from './GraficoCategorias';
import { SaldoInicial } from './SaldoInicial';
import type { PropsModo } from '../../pages/tiposModo';
import type { ResumoAno, ResumoMes } from '../../types/api';

/** O que um widget recebe para se desenhar: os dados do mês e as ações. */
export interface ContextoWidget extends PropsModo {
  /** Já resolvidos por `ModoEstatico` — todo widget precisa dos dois. */
  resumo: ResumoAno;
  mesResumo: ResumoMes;
  arquivado: boolean;
}

interface DefinicaoWidget {
  /** Nome no menu de adicionar. Não é o título do card — esse vem do próprio. */
  nome: string;
  /** Tamanho com que o bloco nasce, em unidades de grade (12 colunas). */
  tamanho: { w: number; h: number };
  desenhar: (ctx: ContextoWidget) => ReactNode;
}

export const CATALOGO = {
  saldo: {
    nome: 'Saldo do mês',
    tamanho: { w: 4, h: 5 },
    desenhar: (c) => <TotaisMes mes={c.mesResumo} preencher />,
  },

  patrimonio: {
    nome: 'Patrimônio guardado',
    tamanho: { w: 4, h: 5 },
    desenhar: (c) => <TotalGuardado resumo={c.resumo} preencher />,
  },

  'gastos-rosca': {
    nome: 'Gastos por categoria (rosca)',
    tamanho: { w: 4, h: 6 },
    desenhar: (c) => (
      <GraficoCategorias mes={c.mesResumo} categorias={c.categorias} />
    ),
  },

  'gastos-tabela': {
    nome: 'Gastos por categoria (lista)',
    tamanho: { w: 4, h: 6 },
    desenhar: (c) => (
      <GastosPorCategoria mes={c.mesResumo} categorias={c.categorias} preencher />
    ),
  },

  'despesas-diarias': {
    nome: 'Despesas diárias',
    tamanho: { w: 4, h: 6 },
    desenhar: (c) => (
      <DespesasDiarias
        lancamentos={c.lancamentos}
        ano={c.anoAtual}
        mes={c.mesAtual}
      />
    ),
  },

  calendario: {
    nome: 'Calendário de vencimentos',
    tamanho: { w: 6, h: 7 },
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
              e instanceof Error
                ? e.message
                : 'Não foi possível atualizar a fatura.',
            );
          }
        }}
      />
    ),
  },

  'contas-recorrentes': {
    nome: 'Contas recorrentes',
    tamanho: { w: 6, h: 7 },
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

  'saldo-inicial': {
    nome: 'Abertura do mês',
    tamanho: { w: 4, h: 4 },
    desenhar: (c) => <SaldoInicial mes={c.mesResumo} />,
  },

  wishlist: {
    nome: 'Wishlist',
    tamanho: { w: 4, h: 5 },
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

  'fatura-cartao': {
    nome: 'Fatura do cartão',
    tamanho: { w: 4, h: 5 },
    desenhar: (c) => (
      <FaturaCartao
        contas={c.contas}
        posicaoCartoes={c.mesResumo.por_cartao}
        faturas={c.faturas}
      />
    ),
  },

  lancamentos: {
    nome: 'Lançamentos do mês',
    tamanho: { w: 12, h: 8 },
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
} satisfies Record<string, DefinicaoWidget>;

export type IdWidget = keyof typeof CATALOGO;

/** Ids na ordem em que aparecem no menu de adicionar. */
export const ID_WIDGETS = Object.keys(CATALOGO) as IdWidget[];

export const TAMANHO_PADRAO: Record<IdWidget, { w: number; h: number }> =
  Object.fromEntries(
    ID_WIDGETS.map((id) => [id, CATALOGO[id].tamanho]),
  ) as Record<IdWidget, { w: number; h: number }>;
