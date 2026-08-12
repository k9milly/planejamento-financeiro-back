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
  | 'rendimento'
  | 'perda'
  | 'transferencia';

export type DestinoRendimento = 'conta' | 'guardado';

export interface Conta {
  id: number;
  nome: string;
  cor: string;
  ordem: number;
  ativa: boolean;
}

export interface SaldoInicial {
  conta_id: number;
  saldo: string;
  guardado: string;
}

/** Como uma conta fechou o período. */
export interface CarteirasConta {
  conta_id: number;
  nome: string;
  cor: string;
  saldo: string;
  guardado: string;
}
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
  conta_id: number;
  conta_destino_id: number | null;
  conta: Conta;
  destino: DestinoRendimento | null;
  categoria_id: number | null;
  categoria: Categoria | null;
  descricao: string;
  fitid: string | null;
}

export interface NovoLancamento {
  data: string;
  valor: string;
  tipo: TipoLancamento;
  conta_id: number;
  conta_destino_id?: number | null;
  destino?: DestinoRendimento | null;
  categoria_id?: number | null;
  descricao?: string;
}

export interface Ano {
  id: number;
  ano: number;
  arquivado: boolean;
  arquivado_em: string | null;
  criado_em: string;
  saldos_iniciais: SaldoInicial[];
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
  rendimentos: string;
  perdas: string;
  /** Quanto circulou entre contas suas. Não entra em entradas nem saídas. */
  transferido: string;
  por_conta: CarteirasConta[];
  gastos_por_categoria: GastoCategoria[];
}

export interface ResumoAno {
  ano: number;
  arquivado: boolean;
  total_guardado: string;
  saldo_final: string;
  total_entradas: string;
  total_saidas: string;
  por_conta: CarteirasConta[];
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
  conta_id: number;
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
  conta_id: number;
  conta_destino_id?: number | null;
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
