"""Schemas Pydantic: o contrato da API.

Os tipos aqui são a fonte da verdade para os tipos TypeScript do frontend
(`frontend/src/types/api.ts`) — ao mexer em um, mexa no outro.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    DestinoRendimento,
    FormaPagamento,
    Importancia,
    SituacaoGastoFixo,
    TipoConta,
    TipoLancamento,
)


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Contas
# --------------------------------------------------------------------------- #
class ContaCriar(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    cor: str = Field(default="#8d7799", pattern=r"^#[0-9a-fA-F]{6}$")
    ordem: int = 0
    tipo: TipoConta = TipoConta.CORRENTE
    # Só relevante para tipo=cartao_credito.
    dia_vencimento_fatura: int | None = Field(default=None, ge=1, le=31)
    conta_pagamento_padrao_id: int | None = None

    @model_validator(mode="after")
    def _coerencia_tipo(self) -> "ContaCriar":
        _validar_coerencia_conta(
            self.tipo, self.dia_vencimento_fatura, self.conta_pagamento_padrao_id,
            ValueError,
        )
        return self


class ContaAtualizar(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=60)
    cor: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    ordem: int | None = None
    ativa: bool | None = None
    tipo: TipoConta | None = None
    dia_vencimento_fatura: int | None = Field(default=None, ge=1, le=31)
    conta_pagamento_padrao_id: int | None = None


class ContaOut(_Base):
    id: int
    nome: str
    cor: str
    ordem: int
    ativa: bool
    tipo: TipoConta
    dia_vencimento_fatura: int | None
    conta_pagamento_padrao_id: int | None


def _validar_coerencia_conta(
    tipo: TipoConta,
    dia_vencimento_fatura: int | None,
    conta_pagamento_padrao_id: int | None,
    erro,
) -> None:
    """`dia_vencimento_fatura`/`conta_pagamento_padrao_id` só existem para
    cartões, e um cartão precisa do dia de vencimento para poder lembrar."""
    if tipo is TipoConta.CARTAO_CREDITO:
        if dia_vencimento_fatura is None:
            raise erro(
                "Um cartão de crédito precisa de um dia de vencimento da fatura."
            )
    else:
        if dia_vencimento_fatura is not None:
            raise erro("'dia_vencimento_fatura' só se aplica a cartões de crédito.")
        if conta_pagamento_padrao_id is not None:
            raise erro(
                "'conta_pagamento_padrao_id' só se aplica a cartões de crédito."
            )


class SaldoInicialDefinir(BaseModel):
    """Quanto havia na conta antes do primeiro lançamento do ano."""

    conta_id: int
    saldo: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    guardado: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)


class SaldoInicialOut(_Base):
    conta_id: int
    saldo: Decimal
    guardado: Decimal


# --------------------------------------------------------------------------- #
# Categorias
# --------------------------------------------------------------------------- #
class CategoriaCriar(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    cor: str = Field(default="#94a3b8", pattern=r"^#[0-9a-fA-F]{6}$")


class CategoriaAtualizar(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=60)
    cor: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    ativa: bool | None = None


class CategoriaOut(_Base):
    id: int
    nome: str
    cor: str
    ativa: bool


# --------------------------------------------------------------------------- #
# Preferências (cores da forma de pagamento, layout do painel)
# --------------------------------------------------------------------------- #
class CorFormaPagamentoDefinir(BaseModel):
    cor: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class CorFormaPagamentoOut(_Base):
    forma_pagamento: FormaPagamento
    cor: str


class LayoutDashboardDefinir(BaseModel):
    """`layout` é uma string opaca: JSON serializado pelo frontend.

    O backend não valida o conteúdo de propósito — ver `Usuario.layout_dashboard`.
    """

    layout: str


class LayoutDashboardOut(BaseModel):
    layout: str | None


# --------------------------------------------------------------------------- #
# Lançamentos
# --------------------------------------------------------------------------- #
class LancamentoBase(BaseModel):
    data: date
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    tipo: TipoLancamento
    conta_id: int
    conta_destino_id: int | None = None
    destino: DestinoRendimento | None = None
    categoria_id: int | None = None
    forma_pagamento: FormaPagamento | None = None
    descricao: str = ""

    @model_validator(mode="after")
    def _coerencia(self) -> "LancamentoBase":
        """Impede combinações que tornariam os totais ambíguos.

        Não checa aqui se `conta_id` é do tipo certo (corrente/cartão) — isso
        depende de olhar o banco, e quem faz é o router, com
        `validar_conta_compativel`, depois de buscar a conta.
        """
        validar_coerencia(
            self.tipo, self.destino, self.categoria_id, self.conta_id,
            self.conta_destino_id, self.forma_pagamento, ValueError,
        )
        return self


# Tipos que dependem de saber qual carteira foi afetada.
TIPOS_COM_DESTINO = {TipoLancamento.RENDIMENTO, TipoLancamento.PERDA}


def validar_coerencia(
    tipo: TipoLancamento,
    destino: DestinoRendimento | None,
    categoria_id: int | None,
    conta_id: int,
    conta_destino_id: int | None,
    forma_pagamento: FormaPagamento | None,
    erro,
) -> None:
    """Regras de combinação entre os campos de um lançamento.

    Vive fora do schema porque também precisa rodar sobre o objeto já mesclado
    de um PATCH e sobre as linhas confirmadas na importação — três caminhos que
    precisam concordar. Recebe a classe de erro a levantar para servir tanto ao
    Pydantic (ValueError) quanto aos routers (HTTPException).

    Não valida aqui se a conta usada é do tipo certo (corrente/cartão) — essa
    regra depende do tipo da `Conta` no banco; ver `validar_conta_compativel`,
    chamada pelos routers depois de buscar a conta envolvida.
    """
    if tipo in TIPOS_COM_DESTINO and destino is None:
        raise erro(
            f"Lançamento do tipo '{tipo.value}' exige 'destino': "
            "'conta' ou 'guardado'."
        )
    if tipo not in TIPOS_COM_DESTINO and destino is not None:
        raise erro("'destino' só se aplica a rendimento e perda.")

    if tipo is not TipoLancamento.SAIDA and categoria_id is not None:
        raise erro("Somente lançamentos do tipo saída podem ter categoria.")

    if tipo is not TipoLancamento.SAIDA and forma_pagamento is not None:
        raise erro("'forma_pagamento' só se aplica a lançamentos do tipo saída.")

    if tipo is TipoLancamento.TRANSFERENCIA:
        if conta_destino_id is None:
            raise erro("Transferência exige a conta de destino.")
        if conta_destino_id == conta_id:
            raise erro("A conta de destino precisa ser diferente da de origem.")
    elif conta_destino_id is not None:
        raise erro("'conta_destino_id' só se aplica a transferências.")


def validar_conta_compativel(
    tipo: TipoLancamento,
    forma_pagamento: FormaPagamento | None,
    conta_tipo: TipoConta,
    erro,
) -> None:
    """Se a conta usada como origem é do tipo certo para a operação.

    Regra do ADR-0002: dinheiro só *sai* de um cartão através do pagamento de
    fatura (que é uma transferência, não uma saída) — então toda saída, seja
    qual for a forma de pagamento, e todo lançamento que não seja saída ou
    transferência, exige conta corrente. Só a saída no crédito exige cartão.
    """
    exige_cartao = (
        tipo is TipoLancamento.SAIDA and forma_pagamento is FormaPagamento.CREDITO
    )
    if exige_cartao and conta_tipo is not TipoConta.CARTAO_CREDITO:
        raise erro("Pagamento no crédito exige uma conta do tipo cartão.")
    if not exige_cartao and conta_tipo is not TipoConta.CORRENTE:
        raise erro("Esta forma de pagamento não se aplica a um cartão de crédito.")


class LancamentoCriar(LancamentoBase):
    pass


class LancamentoAtualizar(BaseModel):
    """Atualização parcial. A coerência é revalidada no router, sobre o objeto
    já mesclado — validar campo a campo aqui deixaria passar combinações ruins."""

    data: date | None = None
    valor: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    tipo: TipoLancamento | None = None
    conta_id: int | None = None
    conta_destino_id: int | None = None
    destino: DestinoRendimento | None = None
    categoria_id: int | None = None
    forma_pagamento: FormaPagamento | None = None
    descricao: str | None = None


class LancamentoOut(_Base):
    id: int
    ano_id: int
    mes: int
    data: date
    valor: Decimal
    tipo: TipoLancamento
    conta_id: int
    conta_destino_id: int | None
    conta: ContaOut
    destino: DestinoRendimento | None
    categoria_id: int | None
    categoria: CategoriaOut | None
    forma_pagamento: FormaPagamento | None
    descricao: str
    fitid: str | None


# --------------------------------------------------------------------------- #
# Regras de categorização
# --------------------------------------------------------------------------- #
class RegraCriar(BaseModel):
    padrao: str = Field(min_length=2, max_length=120)
    categoria_id: int


class RegraOut(_Base):
    id: int
    padrao: str
    categoria_id: int
    categoria: CategoriaOut


# --------------------------------------------------------------------------- #
# Importação de extrato
# --------------------------------------------------------------------------- #
class TransacaoPrevia(BaseModel):
    """Uma linha da tela de revisão da importação."""

    fitid: str
    data: date
    valor: Decimal
    descricao: str
    tipo_sugerido: TipoLancamento
    categoria_sugerida_id: int | None
    categoria_sugerida_nome: str | None
    # Já existe um lançamento com este fitid neste ano.
    duplicado: bool
    # Mesma data e mesmo valor de um lançamento existente, mas fitid diferente:
    # provavelmente foi digitado à mão antes de importar.
    possivel_repetido: bool
    fora_do_ano: bool


class PreviaImportacao(BaseModel):
    total_lidas: int
    ja_importadas: int
    transacoes: list[TransacaoPrevia]


class TransacaoConfirmar(BaseModel):
    """Uma transação aprovada pelo usuário, com os ajustes que ele fez."""

    fitid: str
    data: date
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    tipo: TipoLancamento
    conta_id: int
    conta_destino_id: int | None = None
    destino: DestinoRendimento | None = None
    categoria_id: int | None = None
    # O extrato bancário não informa a forma de pagamento — nula por padrão,
    # o usuário escolhe na revisão se quiser (ver ADR-0001).
    forma_pagamento: FormaPagamento | None = None
    descricao: str = ""
    # Quando preenchido, cria uma regra para categorizar assim das próximas vezes.
    aprender_padrao: str | None = None


class ConfirmarImportacao(BaseModel):
    transacoes: list[TransacaoConfirmar]


class ResultadoImportacao(BaseModel):
    importadas: int
    ignoradas_duplicadas: int
    regras_criadas: int


# --------------------------------------------------------------------------- #
# Anos
# --------------------------------------------------------------------------- #
class AnoCriar(BaseModel):
    ano: int = Field(ge=1900, le=2200)
    # Aberturas por conta. Contas omitidas começam zeradas.
    saldos_iniciais: list[SaldoInicialDefinir] = []


class AnoOut(_Base):
    id: int
    ano: int
    arquivado: bool
    arquivado_em: datetime | None
    criado_em: datetime
    saldos_iniciais: list[SaldoInicialOut] = []


# --------------------------------------------------------------------------- #
# Gastos fixos
# --------------------------------------------------------------------------- #
class GastoFixoCriar(BaseModel):
    descricao: str = Field(min_length=1, max_length=120)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    dia_vencimento: int = Field(default=1, ge=1, le=31)
    # Enum de verdade, que passa a alimentar a regra "crédito exige cartão"
    # (ver `validar_conta_compativel`). `forma_pagamento_legado` é só o texto
    # livre de antes, mantido para exibição do que já estava escrito.
    forma_pagamento: FormaPagamento | None = None
    forma_pagamento_legado: str = ""
    categoria_id: int | None = None
    # De qual conta esta despesa sai; usada ao gerar o lançamento do mês. Pode
    # ser um cartão quando `forma_pagamento == credito`.
    conta_id: int


class GastoFixoAtualizar(BaseModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=120)
    valor: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    dia_vencimento: int | None = Field(default=None, ge=1, le=31)
    forma_pagamento: FormaPagamento | None = None
    forma_pagamento_legado: str | None = None
    categoria_id: int | None = None
    conta_id: int | None = None
    ativo: bool | None = None


class GastoFixoMensalOut(_Base):
    mes: int
    situacao: SituacaoGastoFixo
    lancamento_id: int | None


class GastoFixoOut(_Base):
    id: int
    ano_id: int
    descricao: str
    valor: Decimal
    dia_vencimento: int
    forma_pagamento: FormaPagamento | None
    forma_pagamento_legado: str
    categoria_id: int | None
    conta_id: int
    ativo: bool
    meses: list[GastoFixoMensalOut] = []


# --------------------------------------------------------------------------- #
# Fatura do cartão de crédito
# --------------------------------------------------------------------------- #
class FaturaPagar(BaseModel):
    """Corpo opcional do pagamento: de qual conta o dinheiro sai.

    Quando omitido, usa `conta_pagamento_padrao_id` do cartão — 422 se nenhum
    dos dois existir, porque não há como pagar sem saber de onde sai o dinheiro.
    """

    conta_pagamento_id: int | None = None


class FaturaOut(BaseModel):
    """A fatura em aberto de um cartão em um mês: valor e situação."""

    cartao_id: int
    ano: int
    mes: int
    valor_em_aberto: Decimal
    situacao: SituacaoGastoFixo
    lancamento_id: int | None
    # Espelha `Conta.dia_vencimento_fatura`. Vem junto para o calendário de
    # vencimentos não precisar cruzar esta resposta com a lista de contas.
    dia_vencimento: int


# --------------------------------------------------------------------------- #
# Wishlist
# --------------------------------------------------------------------------- #
class DesejoCriar(BaseModel):
    desejo: str = Field(min_length=1, max_length=120)
    valor: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    importancia: Importancia = Importancia.MEDIA
    somar: bool = False


class DesejoAtualizar(BaseModel):
    desejo: str | None = Field(default=None, min_length=1, max_length=120)
    valor: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    importancia: Importancia | None = None
    somar: bool | None = None
    comprado: bool | None = None


class DesejoOut(_Base):
    id: int
    ano_id: int
    desejo: str
    valor: Decimal
    importancia: Importancia
    somar: bool
    comprado: bool


# --------------------------------------------------------------------------- #
# Resumos (o que alimenta os containers da tela)
# --------------------------------------------------------------------------- #
class GastoCategoriaOut(BaseModel):
    categoria: str
    total: Decimal
    percentual: float


class CarteirasContaOut(BaseModel):
    """Como uma conta fechou o mês."""

    conta_id: int
    nome: str
    cor: str
    saldo: Decimal
    guardado: Decimal


class ResumoMesOut(BaseModel):
    """Alimenta o container 'Total de {mês}' e o de gastos por categoria."""

    mes: int
    nome_mes: str
    entradas: Decimal
    saidas: Decimal
    guardado_no_mes: Decimal
    saldo: Decimal
    saldo_inicial: Decimal
    guardado_acumulado: Decimal
    rendimentos: Decimal
    perdas: Decimal
    # Quanto circulou entre contas suas. Não entra em entradas nem saídas;
    # aparece só para você conferir que o valor bate com o extrato.
    transferido: Decimal
    por_conta: list[CarteirasContaOut]
    # Fatura em aberto de cada cartão ao fim do mês. `saldo` aqui é <= 0 (a
    # dívida); `guardado` é sempre "0.00" — reaproveita `CarteirasContaOut`
    # porque tem o mesmo formato, não por ser a mesma coisa.
    por_cartao: list[CarteirasContaOut]
    gastos_por_categoria: list[GastoCategoriaOut]


class ResumoAnoOut(BaseModel):
    """Alimenta o container 'Total guardado': linha por mês + total geral."""

    ano: int
    arquivado: bool
    total_guardado: Decimal
    saldo_final: Decimal
    total_entradas: Decimal
    total_saidas: Decimal
    por_conta: list[CarteirasContaOut]
    por_cartao: list[CarteirasContaOut]
    meses: list[ResumoMesOut]
