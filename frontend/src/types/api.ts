/**
 * Espelho dos schemas Pydantic do backend (`backend/app/schemas.py`).
 * Ao mudar um contrato lá, mude aqui também.
 *
 * Valores monetários chegam como string decimal ("1234.56") e não como number:
 * o backend usa Decimal e serializar para float perderia centavos. Converta
 * apenas na hora de exibir, com os helpers de `lib/formato.ts`.
 */

export type TipoLancamento =
  | 'entrada'
  | 'saida'
  | 'guardado'
  | 'retirado'
  | 'rendimento';

export type DestinoRendimento = 'conta' | 'guardado';
export type Importancia = 'baixa' | 'media' | 'alta';
export type SituacaoGastoFixo = 'pendente' | 'pago';

export interface Categoria {
  id: number;
  nome: string;
  cor: string;
  ativa: boolean;
}

export interface Lancamento {
  id: number;
  ano_id: number;
  mes: number;
  data: string;
  valor: string;
  tipo: TipoLancamento;
  destino: DestinoRendimento | null;
  categoria_id: number | null;
  categoria: Categoria | null;
  descricao: string;
}

export interface NovoLancamento {
  data: string;
  valor: string;
  tipo: TipoLancamento;
  destino?: DestinoRendimento | null;
  categoria_id?: number | null;
  descricao?: string;
}

export interface Ano {
  id: number;
  ano: number;
  saldo_inicial_conta: string;
  saldo_inicial_guardado: string;
  arquivado: boolean;
  arquivado_em: string | null;
  criado_em: string;
}

export interface GastoCategoria {
  categoria: string;
  total: string;
  percentual: number;
}

export interface ResumoMes {
  mes: number;
  nome_mes: string;
  entradas: string;
  saidas: string;
  guardado_no_mes: string;
  saldo: string;
  saldo_inicial: string;
  guardado_acumulado: string;
  rendimento_conta: string;
  rendimento_guardado: string;
  gastos_por_categoria: GastoCategoria[];
}

export interface ResumoAno {
  ano: number;
  arquivado: boolean;
  saldo_inicial_conta: string;
  saldo_inicial_guardado: string;
  total_guardado: string;
  saldo_final: string;
  total_entradas: string;
  total_saidas: string;
  meses: ResumoMes[];
}

export interface GastoFixoMensal {
  mes: number;
  situacao: SituacaoGastoFixo;
  lancamento_id: number | null;
}

export interface GastoFixo {
  id: number;
  ano_id: number;
  descricao: string;
  valor: string;
  dia_vencimento: number;
  forma_pagamento: string;
  categoria_id: number | null;
  ativo: boolean;
  meses: GastoFixoMensal[];
}

export interface Desejo {
  id: number;
  ano_id: number;
  desejo: string;
  valor: string;
  importancia: Importancia;
  somar: boolean;
  comprado: boolean;
}

export interface TotalWishlist {
  total_marcado: string;
  total_geral: string;
  quantidade_marcada: number;
}

export interface Regra {
  id: number;
  padrao: string;
  categoria_id: number;
  categoria: Categoria;
}

export interface TransacaoPrevia {
  fitid: string;
  data: string;
  valor: string;
  descricao: string;
  tipo_sugerido: TipoLancamento;
  categoria_sugerida_id: number | null;
  categoria_sugerida_nome: string | null;
  duplicado: boolean;
  possivel_repetido: boolean;
  fora_do_ano: boolean;
}

export interface PreviaImportacao {
  total_lidas: number;
  ja_importadas: number;
  transacoes: TransacaoPrevia[];
}

export interface TransacaoConfirmar {
  fitid: string;
  data: string;
  valor: string;
  tipo: TipoLancamento;
  destino?: DestinoRendimento | null;
  categoria_id?: number | null;
  descricao?: string;
  aprender_padrao?: string | null;
}

export interface ResultadoImportacao {
  importadas: number;
  ignoradas_duplicadas: number;
  regras_criadas: number;
}
