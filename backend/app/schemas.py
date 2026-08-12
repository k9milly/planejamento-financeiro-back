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
    Importancia,
    SituacaoGastoFixo,
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


class ContaAtualizar(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=60)
    cor: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    ordem: int | None = None
    ativa: bool | None = None


class ContaOut(_Base):
    id: int
    nome: str
    cor: str
    ordem: int
    ativa: bool


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
    descricao: str = ""

    @model_validator(mode="after")
    def _coerencia(self) -> "LancamentoBase":
        """Impede combinações que tornariam os totais ambíguos."""
        validar_coerencia(
            self.tipo, self.destino, self.categoria_id, self.conta_id,
            self.conta_destino_id, ValueError,
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
    erro,
) -> None:
    """Regras de combinação entre os campos de um lançamento.

    Vive fora do schema porque também precisa rodar sobre o objeto já mesclado
    de um PATCH e sobre as linhas confirmadas na importação — três caminhos que
    precisam concordar. Recebe a classe de erro a levantar para servir tanto ao
    Pydantic (ValueError) quanto aos routers (HTTPException).
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

    if tipo is TipoLancamento.TRANSFERENCIA:
        if conta_destino_id is None:
            raise erro("Transferência exige a conta de destino.")
        if conta_destino_id == conta_id:
            raise erro("A conta de destino precisa ser diferente da de origem.")
    elif conta_destino_id is not None:
        raise erro("'conta_destino_id' só se aplica a transferências.")


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
    forma_pagamento: str = ""
    categoria_id: int | None = None
    # De qual conta esta despesa sai; usada ao gerar o lançamento do mês.
    conta_id: int


class GastoFixoAtualizar(BaseModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=120)
    valor: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    dia_vencimento: int | None = Field(default=None, ge=1, le=31)
    forma_pagamento: str | None = None
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
    forma_pagamento: str
    categoria_id: int | None
    conta_id: int
    ativo: bool
    meses: list[GastoFixoMensalOut] = []


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
    meses: list[ResumoMesOut]
