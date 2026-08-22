/** Cliente HTTP da API. Uma função por endpoint, sem biblioteca externa. */

import type {
  Ano,
  Categoria,
  Conta,
  CorPagamento,
  Desejo,
  Fatura,
  FormaPagamento,
  GastoFixo,
  Importancia,
  LayoutDashboard,
  SaldoInicial,
  Lancamento,
  NovoLancamento,
  PreviaImportacao,
  Regra,
  ResultadoImportacao,
  ResumoAno,
  TipoConta,
  TotalWishlist,
  TransacaoConfirmar,
} from '../types/api';

import { sessao } from './sessao';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/** Erro com a mensagem que o backend mandou, para exibir direto na tela. */
export class ErroApi extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ErroApi';
  }
}

function requisitar<T>(caminho: string, init?: RequestInit): Promise<T> {
  return requisitarBruto<T>(caminho, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
}

/**
 * Igual a `requisitar`, mas sem impor o Content-Type.
 *
 * Necessário para o upload do extrato: com FormData, o navegador precisa
 * definir o cabeçalho ele mesmo para incluir o `boundary` do multipart. Fixar
 * `application/json` ali faria o servidor recusar o arquivo.
 */
async function requisitarBruto<T>(
  caminho: string,
  init?: RequestInit,
): Promise<T> {
  const token = sessao.ler();
  const resposta = await fetch(`${BASE}${caminho}`, {
    ...init,
    headers: {
      ...init?.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  // Token vencido ou inválido: derruba a sessão e deixa o app voltar ao login,
  // em vez de encher a tela de erros a cada requisição.
  if (resposta.status === 401 && !caminho.startsWith('/auth/login')) {
    sessao.expirou();
    throw new ErroApi('Sessão expirada. Entre novamente.', 401);
  }

  if (!resposta.ok) {
    // O FastAPI devolve {detail: "..."} ou {detail: [{msg: "..."}]} conforme o
    // erro venha de uma HTTPException ou da validação do Pydantic.
    let mensagem = `Erro ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (typeof corpo.detail === 'string') {
        mensagem = corpo.detail;
      } else if (Array.isArray(corpo.detail)) {
        mensagem = corpo.detail.map((d: { msg: string }) => d.msg).join('; ');
      }
    } catch {
      // Resposta sem corpo JSON: fica a mensagem genérica.
    }
    throw new ErroApi(mensagem, resposta.status);
  }

  return resposta.status === 204 ? (undefined as T) : resposta.json();
}

export const api = {
  login: async (email: string, senha: string) => {
    const dados = await requisitar<{ token: string; email: string }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, senha }) },
    );
    sessao.guardar(dados.token);
    return dados;
  },

  eu: () => requisitar<{ id: number; email: string }>('/auth/eu'),

  sair: () => sessao.limpar(),

  listarAnos: () => requisitar<Ano[]>('/anos'),

  criarAno: (ano: number) =>
    requisitar<Ano>('/anos', { method: 'POST', body: JSON.stringify({ ano }) }),

  arquivarAno: (ano: number) =>
    requisitar<Ano>(`/anos/${ano}/arquivar`, { method: 'POST' }),

  desarquivarAno: (ano: number) =>
    requisitar<Ano>(`/anos/${ano}/desarquivar`, { method: 'POST' }),

  resumo: (ano: number) => requisitar<ResumoAno>(`/anos/${ano}/resumo`),

  listarContas: (tipo?: TipoConta) =>
    requisitar<Conta[]>(`/contas${tipo ? `?tipo=${tipo}` : ''}`),

  criarConta: (dados: {
    nome: string;
    cor?: string;
    ordem?: number;
    tipo?: TipoConta;
    dia_vencimento_fatura?: number | null;
    conta_pagamento_padrao_id?: number | null;
  }) =>
    requisitar<Conta>('/contas', {
      method: 'POST',
      body: JSON.stringify({ ordem: 0, ...dados }),
    }),

  atualizarConta: (
    id: number,
    dados: Partial<{
      nome: string;
      cor: string;
      ordem: number;
      ativa: boolean;
      tipo: TipoConta;
      dia_vencimento_fatura: number | null;
      conta_pagamento_padrao_id: number | null;
    }>,
  ) =>
    requisitar<Conta>(`/contas/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(dados),
    }),

  excluirConta: (id: number) =>
    requisitar<void>(`/contas/${id}`, { method: 'DELETE' }),

  definirSaldosIniciais: (ano: number, saldos: SaldoInicial[]) =>
    requisitar<Ano>(`/anos/${ano}/saldos-iniciais`, {
      method: 'PUT',
      body: JSON.stringify(saldos),
    }),

  listarCategorias: () => requisitar<Categoria[]>('/categorias'),

  criarCategoria: (nome: string, cor?: string) =>
    requisitar<Categoria>('/categorias', {
      method: 'POST',
      body: JSON.stringify({ nome, ...(cor ? { cor } : {}) }),
    }),

  atualizarCategoria: (
    id: number,
    dados: Partial<{ nome: string; cor: string; ativa: boolean }>,
  ) =>
    requisitar<Categoria>(`/categorias/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(dados),
    }),

  excluirCategoria: (id: number) =>
    requisitar<void>(`/categorias/${id}`, { method: 'DELETE' }),

  listarLancamentos: (ano: number, mes?: number) =>
    requisitar<Lancamento[]>(
      `/anos/${ano}/lancamentos${mes ? `?mes=${mes}` : ''}`,
    ),

  criarLancamento: (ano: number, dados: NovoLancamento) =>
    requisitar<Lancamento>(`/anos/${ano}/lancamentos`, {
      method: 'POST',
      body: JSON.stringify(dados),
    }),

  atualizarLancamento: (
    ano: number,
    id: number,
    dados: Partial<NovoLancamento>,
  ) =>
    requisitar<Lancamento>(`/anos/${ano}/lancamentos/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(dados),
    }),

  excluirLancamento: (ano: number, id: number) =>
    requisitar<void>(`/anos/${ano}/lancamentos/${id}`, { method: 'DELETE' }),

  listarGastosFixos: (ano: number) =>
    requisitar<GastoFixo[]>(`/anos/${ano}/gastos-fixos`),

  criarGastoFixo: (
    ano: number,
    dados: {
      descricao: string;
      valor: string;
      dia_vencimento: number;
      conta_id: number;
      categoria_id?: number | null;
      forma_pagamento?: FormaPagamento | null;
    },
  ) =>
    requisitar<GastoFixo>(`/anos/${ano}/gastos-fixos`, {
      method: 'POST',
      body: JSON.stringify(dados),
    }),

  atualizarGastoFixo: (
    ano: number,
    id: number,
    dados: Partial<{
      descricao: string;
      valor: string;
      dia_vencimento: number;
      conta_id: number;
      categoria_id: number | null;
      forma_pagamento: FormaPagamento | null;
      ativo: boolean;
    }>,
  ) =>
    requisitar<GastoFixo>(`/anos/${ano}/gastos-fixos/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(dados),
    }),

  excluirGastoFixo: (ano: number, id: number) =>
    requisitar<void>(`/anos/${ano}/gastos-fixos/${id}`, { method: 'DELETE' }),

  pagarGastoFixo: (ano: number, id: number, mes: number) =>
    requisitar<Lancamento>(`/anos/${ano}/gastos-fixos/${id}/meses/${mes}/pagar`, {
      method: 'POST',
    }),

  desfazerGastoFixo: (ano: number, id: number, mes: number) =>
    requisitar<void>(`/anos/${ano}/gastos-fixos/${id}/meses/${mes}/desfazer`, {
      method: 'POST',
    }),

  listarWishlist: (ano: number) => requisitar<Desejo[]>(`/anos/${ano}/wishlist`),

  totalWishlist: (ano: number) =>
    requisitar<TotalWishlist>(`/anos/${ano}/wishlist/total`),

  criarDesejo: (
    ano: number,
    dados: { desejo: string; valor: string; importancia: Importancia },
  ) =>
    requisitar<Desejo>(`/anos/${ano}/wishlist`, {
      method: 'POST',
      body: JSON.stringify(dados),
    }),

  atualizarDesejo: (
    ano: number,
    id: number,
    dados: Partial<{
      desejo: string;
      valor: string;
      importancia: Importancia;
      somar: boolean;
      comprado: boolean;
    }>,
  ) =>
    requisitar<Desejo>(`/anos/${ano}/wishlist/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(dados),
    }),

  excluirDesejo: (ano: number, id: number) =>
    requisitar<void>(`/anos/${ano}/wishlist/${id}`, { method: 'DELETE' }),

  listarRegras: () => requisitar<Regra[]>('/regras'),

  excluirRegra: (id: number) =>
    requisitar<void>(`/regras/${id}`, { method: 'DELETE' }),

  /** Envia o extrato e recebe a prévia. Nada é gravado nesta chamada. */
  previaOfx: async (ano: number, arquivo: File) => {
    const corpo = new FormData();
    corpo.append('arquivo', arquivo);
    // Sem Content-Type manual: o navegador precisa gerar o boundary do multipart.
    return requisitarBruto<PreviaImportacao>(
      `/anos/${ano}/importacao/ofx/previa`,
      { method: 'POST', body: corpo },
    );
  },

  confirmarOfx: (ano: number, transacoes: TransacaoConfirmar[]) =>
    requisitar<ResultadoImportacao>(`/anos/${ano}/importacao/ofx/confirmar`, {
      method: 'POST',
      body: JSON.stringify({ transacoes }),
    }),

  fatura: (ano: number, cartaoId: number, mes: number) =>
    requisitar<Fatura>(`/anos/${ano}/cartoes/${cartaoId}/fatura/${mes}`),

  pagarFatura: (
    ano: number,
    cartaoId: number,
    mes: number,
    contaPagamentoId?: number | null,
  ) =>
    requisitar<Lancamento>(`/anos/${ano}/cartoes/${cartaoId}/fatura/${mes}/pagar`, {
      method: 'POST',
      ...(contaPagamentoId
        ? { body: JSON.stringify({ conta_pagamento_id: contaPagamentoId }) }
        : {}),
    }),

  desfazerFatura: (ano: number, cartaoId: number, mes: number) =>
    requisitar<void>(`/anos/${ano}/cartoes/${cartaoId}/fatura/${mes}/desfazer`, {
      method: 'POST',
    }),

  listarCoresPagamento: () =>
    requisitar<CorPagamento[]>('/preferencias/cores-forma-pagamento'),

  definirCorPagamento: (forma: FormaPagamento, cor: string) =>
    requisitar<CorPagamento>(`/preferencias/cores-forma-pagamento/${forma}`, {
      method: 'PUT',
      body: JSON.stringify({ cor }),
    }),

  /**
   * Layout do painel. `layout` é uma string opaca para o servidor: ele guarda
   * e devolve sem olhar dentro (ver `docs/CONTRATO-API.md`), então quem
   * valida o conteúdo é `lib/layoutDashboard.ts`.
   */
  layoutDashboard: () =>
    requisitar<LayoutDashboard>('/preferencias/layout-dashboard'),

  salvarLayoutDashboard: (layout: string) =>
    requisitar<LayoutDashboard>('/preferencias/layout-dashboard', {
      method: 'PUT',
      body: JSON.stringify({ layout }),
    }),
};
