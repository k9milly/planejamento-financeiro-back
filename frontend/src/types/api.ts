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

export type TipoConta = 'corrente' | 'cartao_credito';

/** Como uma saída foi paga. `null`/ausente é tratado como 'debito'. */
export type FormaPagamento = 'credito' | 'debito' | 'pix' | 'dinheiro';

export interface Conta {
  id: number;
  nome: string;
  cor: string;
  ordem: number;
  ativa: boolean;
  tipo: TipoConta;
  /** Só preenchido para tipo === 'cartao_credito'. */
  dia_vencimento_fatura: number | null;
  conta_pagamento_padrao_id: number | null;
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
  forma_pagamento: FormaPagamento | null;
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
  forma_pagamento?: FormaPagamento | null;
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
  /** Fatura em aberto de cada cartão ao fim do mês. `saldo` é <= 0 (a dívida). */
  por_cartao: CarteirasConta[];
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
  por_cartao: CarteirasConta[];
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
  forma_pagamento: FormaPagamento | null;
  /** Texto livre digitado antes do enum existir; só exibição. */
  forma_pagamento_legado: string;
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
  forma_pagamento?: FormaPagamento | null;
  descricao?: string;
  aprender_padrao?: string | null;
}

export interface ResultadoImportacao {
  importadas: number;
  ignoradas_duplicadas: number;
  regras_criadas: number;
}

/** Cor de exibição de uma forma de pagamento, guardada no servidor. */
export interface CorPagamento {
  forma_pagamento: FormaPagamento;
  cor: string;
}

/** A fatura em aberto de um cartão em um mês: valor e situação. */
export interface Fatura {
  cartao_id: number;
  ano: number;
  mes: number;
  valor_em_aberto: string;
  situacao: SituacaoGastoFixo;
  lancamento_id: number | null;
}
