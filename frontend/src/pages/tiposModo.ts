/**
 * O pacote de dados e ações que `App.tsx` entrega a um modo de visualização.
 *
 * Os dois modos (planilha e painel) mostram exatamente o mesmo mês, com as
 * mesmas operações de escrita — só mudam o arranjo na tela. Um tipo só,
 * compartilhado, mantém isso verdadeiro: um modo não tem como receber menos
 * do que o outro sem que o TypeScript reclame.
 */

import type { Dispatch, SetStateAction } from 'react';
import type { api } from '../lib/api';
import type { ModoVisual } from '../lib/modoVisual';
import type { Tema } from '../lib/tema';
import type {
  Ano,
  Categoria,
  Conta,
  Desejo,
  Fatura,
  GastoFixo,
  Lancamento,
  ResumoAno,
} from '../types/api';

export interface PropsModo {
  tema: Tema;
  alternar: () => void;
  anos: Ano[];
  anoAtual: number;
  setAnoAtual: (ano: number) => void;
  mesAtual: number;
  setMesAtual: (mes: number) => void;
  resumo: ResumoAno | null;
  lancamentos: Lancamento[];
  categorias: Categoria[];
  contas: Conta[];
  gastosFixos: GastoFixo[];
  desejos: Desejo[];
  faturas: Record<number, Fatura>;
  erro: string;
  setErro: Dispatch<SetStateAction<string>>;
  importando: boolean;
  setImportando: Dispatch<SetStateAction<boolean>>;
  editandoLancamento: Lancamento | null;
  setEditandoLancamento: Dispatch<SetStateAction<Lancamento | null>>;
  recarregar: () => Promise<void>;
  /** Envolve uma escrita: executa, recarrega tudo e mostra o erro na barra. */
  acao: <A extends unknown[]>(
    operacao: (ano: number, ...args: A) => Promise<unknown>,
  ) => (...args: A) => Promise<void>;
  alternarGastoFixo: (gasto: GastoFixo, pago: boolean) => Promise<void>;
  aposMudarCategorias: () => Promise<void>;
  criarCategoriaInline: (nome: string) => Promise<Categoria>;
  atualizarLancamento: (
    id: number,
    dados: Partial<Parameters<typeof api.criarLancamento>[1]>,
  ) => Promise<void>;
  comAnos: (operacao: () => Promise<unknown>, irPara?: number) => Promise<void>;
  aoSair: () => void;
  modo: ModoVisual;
  aoDefinirModo: (modo: ModoVisual) => void;
}
