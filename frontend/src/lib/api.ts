/** Cliente HTTP da API. Uma função por endpoint, sem biblioteca externa. */

import type {
  Ano,
  Categoria,
  Desejo,
  GastoFixo,
  Lancamento,
  NovoLancamento,
  ResumoAno,
  TotalWishlist,
} from '../types/api';

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

async function requisitar<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(`${BASE}${caminho}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });

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
  listarAnos: () => requisitar<Ano[]>('/anos'),

  criarAno: (ano: number) =>
    requisitar<Ano>('/anos', { method: 'POST', body: JSON.stringify({ ano }) }),

  arquivarAno: (ano: number) =>
    requisitar<Ano>(`/anos/${ano}/arquivar`, { method: 'POST' }),

  desarquivarAno: (ano: number) =>
    requisitar<Ano>(`/anos/${ano}/desarquivar`, { method: 'POST' }),

  resumo: (ano: number) => requisitar<ResumoAno>(`/anos/${ano}/resumo`),

  listarCategorias: () => requisitar<Categoria[]>('/categorias'),

  criarCategoria: (nome: string, cor?: string) =>
    requisitar<Categoria>('/categorias', {
      method: 'POST',
      body: JSON.stringify({ nome, ...(cor ? { cor } : {}) }),
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
};
