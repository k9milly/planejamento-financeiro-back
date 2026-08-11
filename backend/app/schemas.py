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
    destino: DestinoRendimento | None = None
    categoria_id: int | None = None
    descricao: str = ""

    @model_validator(mode="after")
    def _coerencia(self) -> "LancamentoBase":
        """Impede combinações que tornariam os totais ambíguos."""
        if self.tipo is TipoLancamento.RENDIMENTO and self.destino is None:
            raise ValueError(
                "Rendimento exige 'destino': 'conta' ou 'guardado'."
            )
        if self.tipo is not TipoLancamento.RENDIMENTO and self.destino is not None:
            raise ValueError("'destino' só se aplica a lançamentos do tipo rendimento.")
        if self.tipo is not TipoLancamento.SAIDA and self.categoria_id is not None:
            raise ValueError(
                "Somente lançamentos do tipo saída podem ter categoria."
            )
        return self


class LancamentoCriar(LancamentoBase):
    pass


class LancamentoAtualizar(BaseModel):
    """Atualização parcial. A coerência é revalidada no router, sobre o objeto
    já mesclado — validar campo a campo aqui deixaria passar combinações ruins."""

    data: date | None = None
    valor: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    tipo: TipoLancamento | None = None
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
    destino: DestinoRendimento | None
    categoria_id: int | None
    categoria: CategoriaOut | None
    descricao: str


# --------------------------------------------------------------------------- #
# Anos
# --------------------------------------------------------------------------- #
class AnoCriar(BaseModel):
    ano: int = Field(ge=1900, le=2200)
    saldo_inicial_conta: Decimal = Field(default=Decimal("0"), max_digits=12,
                                         decimal_places=2)
    saldo_inicial_guardado: Decimal = Field(default=Decimal("0"), max_digits=12,
                                            decimal_places=2)


class AnoOut(_Base):
    id: int
    ano: int
    saldo_inicial_conta: Decimal
    saldo_inicial_guardado: Decimal
    arquivado: bool
    arquivado_em: datetime | None
    criado_em: datetime


# --------------------------------------------------------------------------- #
# Gastos fixos
# --------------------------------------------------------------------------- #
class GastoFixoCriar(BaseModel):
    descricao: str = Field(min_length=1, max_length=120)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    dia_vencimento: int = Field(default=1, ge=1, le=31)
    forma_pagamento: str = ""
    categoria_id: int | None = None


class GastoFixoAtualizar(BaseModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=120)
    valor: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    dia_vencimento: int | None = Field(default=None, ge=1, le=31)
    forma_pagamento: str | None = None
    categoria_id: int | None = None
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
    rendimento_conta: Decimal
    rendimento_guardado: Decimal
    gastos_por_categoria: list[GastoCategoriaOut]


class ResumoAnoOut(BaseModel):
    """Alimenta o container 'Total guardado': linha por mês + total geral."""

    ano: int
    arquivado: bool
    saldo_inicial_conta: Decimal
    saldo_inicial_guardado: Decimal
    total_guardado: Decimal
    saldo_final: Decimal
    total_entradas: Decimal
    total_saidas: Decimal
    meses: list[ResumoMesOut]
