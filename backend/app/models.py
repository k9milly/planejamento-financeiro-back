"""Modelos ORM do Planejamento Financeiro.

O domínio gira em torno de duas "carteiras": a **conta** (dinheiro disponível no
dia a dia) e o **guardado** (a reserva). Todo lançamento afeta uma delas, as
duas, ou move dinheiro entre elas — ver `TipoLancamento`.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TipoLancamento(str, enum.Enum):
    """Como o lançamento movimenta as carteiras.

    ENTRADA    conta += valor            (recebi dinheiro)
    SAIDA      conta -= valor            (gastei da conta)
    GUARDADO   conta -= valor, guardado += valor   (movi para a reserva)
    RETIRADO   guardado -= valor, conta += valor   (tirei da reserva)
    RENDIMENTO carteira indicada por `destino` += valor
    """

    ENTRADA = "entrada"
    SAIDA = "saida"
    GUARDADO = "guardado"
    RETIRADO = "retirado"
    RENDIMENTO = "rendimento"


class DestinoRendimento(str, enum.Enum):
    """Onde o rendimento caiu. Obrigatório apenas quando tipo == RENDIMENTO."""

    CONTA = "conta"
    GUARDADO = "guardado"


class SituacaoGastoFixo(str, enum.Enum):
    PENDENTE = "pendente"
    PAGO = "pago"


class Importancia(str, enum.Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class Ano(Base):
    """Um ano-calendário de planejamento, com seus 12 meses.

    Ao arquivar um ano ele fica somente-leitura, mas continua acessível — é a
    "pasta" de anos anteriores que o usuário consulta quando quiser.
    """

    __tablename__ = "anos"

    id: Mapped[int] = mapped_column(primary_key=True)
    ano: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)

    # Saldos de abertura: o que já existia antes do primeiro lançamento do ano.
    # Quando um ano é gerado a partir do anterior, herdam os saldos de fechamento.
    saldo_inicial_conta: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    saldo_inicial_guardado: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    arquivado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    lancamentos: Mapped[list["Lancamento"]] = relationship(
        back_populates="ano_ref", cascade="all, delete-orphan"
    )
    gastos_fixos: Mapped[list["GastoFixo"]] = relationship(
        back_populates="ano_ref", cascade="all, delete-orphan"
    )
    desejos: Mapped[list["ItemWishlist"]] = relationship(
        back_populates="ano_ref", cascade="all, delete-orphan"
    )


class Categoria(Base):
    """Categoria de gasto. Global (não pertence a um ano) para que os relatórios
    por categoria possam ser comparados entre anos."""

    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    cor: Mapped[str] = mapped_column(String(7), nullable=False, default="#94a3b8")
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    lancamentos: Mapped[list["Lancamento"]] = relationship(back_populates="categoria")


class Lancamento(Base):
    """Uma movimentação individual: o coração da planilha."""

    __tablename__ = "lancamentos"
    __table_args__ = (
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_lancamento_mes"),
        CheckConstraint("valor > 0", name="ck_lancamento_valor_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mes: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)

    # Sempre positivo: o sinal é derivado do tipo, nunca do valor. Isso evita a
    # ambiguidade clássica de "-50 do tipo saída" significar entrada.
    valor: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tipo: Mapped[TipoLancamento] = mapped_column(
        Enum(TipoLancamento, native_enum=False), nullable=False, index=True
    )
    destino: Mapped[DestinoRendimento | None] = mapped_column(
        Enum(DestinoRendimento, native_enum=False), nullable=True
    )

    # Só faz sentido para saídas; os demais tipos não entram no gráfico por categoria.
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    ano_ref: Mapped["Ano"] = relationship(back_populates="lancamentos")
    categoria: Mapped["Categoria | None"] = relationship(back_populates="lancamentos")


class GastoFixo(Base):
    """Despesa recorrente (aluguel, internet, dízimo...).

    É um *modelo*: não movimenta dinheiro sozinho. A cada mês ele pode gerar um
    `Lancamento` de saída — o vínculo fica em `GastoFixoMensal`.
    """

    __tablename__ = "gastos_fixos"
    __table_args__ = (
        CheckConstraint("dia_vencimento BETWEEN 1 AND 31", name="ck_gf_dia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    descricao: Mapped[str] = mapped_column(String(120), nullable=False)
    valor: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    dia_vencimento: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    forma_pagamento: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ano_ref: Mapped["Ano"] = relationship(back_populates="gastos_fixos")
    meses: Mapped[list["GastoFixoMensal"]] = relationship(
        back_populates="gasto_fixo", cascade="all, delete-orphan"
    )


class GastoFixoMensal(Base):
    """Situação de um gasto fixo em um mês específico (pago/pendente)."""

    __tablename__ = "gastos_fixos_mensais"
    __table_args__ = (
        UniqueConstraint("gasto_fixo_id", "mes", name="uq_gasto_fixo_mes"),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_gfm_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    gasto_fixo_id: Mapped[int] = mapped_column(
        ForeignKey("gastos_fixos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    situacao: Mapped[SituacaoGastoFixo] = mapped_column(
        Enum(SituacaoGastoFixo, native_enum=False),
        nullable=False,
        default=SituacaoGastoFixo.PENDENTE,
    )
    # Preenchido quando o gasto fixo vira um lançamento de verdade.
    lancamento_id: Mapped[int | None] = mapped_column(
        ForeignKey("lancamentos.id", ondelete="SET NULL"), nullable=True
    )

    gasto_fixo: Mapped["GastoFixo"] = relationship(back_populates="meses")


class ItemWishlist(Base):
    """Desejo de compra. Não afeta saldo — serve para planejar o uso da reserva."""

    __tablename__ = "wishlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    desejo: Mapped[str] = mapped_column(String(120), nullable=False)
    valor: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    importancia: Mapped[Importancia] = mapped_column(
        Enum(Importancia, native_enum=False), nullable=False, default=Importancia.MEDIA
    )
    # Equivale à coluna "SOMAR" da planilha: só os marcados entram no total.
    somar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comprado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ano_ref: Mapped["Ano"] = relationship(back_populates="desejos")
