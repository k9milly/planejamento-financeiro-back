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
    """Como o lançamento movimenta o dinheiro.

    Cada conta tem duas carteiras: o **saldo** (disponível) e o **guardado**
    (reserva). Todos os efeitos abaixo acontecem dentro da conta do lançamento,
    exceto a transferência, que é a única que envolve duas contas.

    ENTRADA       saldo += valor                     (recebi dinheiro)
    SAIDA         saldo -= valor                     (gastei)
    GUARDADO      saldo -= valor, guardado += valor  (movi para a reserva)
    RETIRADO      guardado -= valor, saldo += valor  (tirei da reserva)
    RENDIMENTO    carteira indicada por `destino` += valor
    PERDA         carteira indicada por `destino` -= valor
    TRANSFERENCIA saldo da conta -= valor, saldo da conta destino += valor

    PERDA existe porque investimento cai. Sem ela, uma queda do ETF teria de ser
    lançada como saída, e apareceria como gasto no relatório por categoria —
    dinheiro que encolheu não é dinheiro que foi consumido.

    TRANSFERENCIA existe porque mover dinheiro entre contas suas não é receita
    nem despesa. Lançar como saída em uma e entrada na outra inflaria os dois
    totais do mês sem que nada tivesse sido gasto ou recebido.
    """

    ENTRADA = "entrada"
    SAIDA = "saida"
    GUARDADO = "guardado"
    RETIRADO = "retirado"
    RENDIMENTO = "rendimento"
    PERDA = "perda"
    TRANSFERENCIA = "transferencia"


class DestinoRendimento(str, enum.Enum):
    """Qual carteira o rendimento ou a perda atinge.

    Obrigatório em RENDIMENTO e PERDA: render na conta corrente e render na
    reserva têm efeitos diferentes no que você tem disponível para gastar.
    """

    CONTA = "conta"
    GUARDADO = "guardado"


class SituacaoGastoFixo(str, enum.Enum):
    PENDENTE = "pendente"
    PAGO = "pago"


class TipoConta(str, enum.Enum):
    """Distingue dinheiro de verdade de dívida de cartão.

    Uma conta corrente é onde o dinheiro está disponível. Um cartão de crédito
    é modelado como uma `Conta` também (ver ADR-0002 em `docs/adr/`), mas o
    "saldo" dele é sempre <= 0: é a fatura em aberto, não dinheiro disponível.
    """

    CORRENTE = "corrente"
    CARTAO_CREDITO = "cartao_credito"


class FormaPagamento(str, enum.Enum):
    """Como uma saída foi paga. Só se aplica a `TipoLancamento.SAIDA`.

    `None` no campo do lançamento é tratado como equivalente a `DEBITO` em
    todo lugar que olha o campo — ver ADR-0001.
    """

    CREDITO = "credito"
    DEBITO = "debito"
    PIX = "pix"
    DINHEIRO = "dinheiro"


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

    arquivado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    saldos_iniciais: Mapped[list["SaldoInicial"]] = relationship(
        back_populates="ano_ref", cascade="all, delete-orphan"
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


class Usuario(Base):
    """Quem pode usar o sistema.

    A senha nunca é guardada: só o hash bcrypt dela. Não há cadastro pela API —
    usuários são criados pelo script `scripts/criar_usuario.py`, rodado por
    quem administra a instalação. Um app de finanças pessoais não tem motivo
    para aceitar cadastro aberto na internet.
    """

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Como o usuário arrumou os blocos do painel. Texto opaco de propósito: é
    # JSON gerado e lido só pelo frontend, e o backend não tem nada a decidir
    # sobre o conteúdo — validar o formato aqui obrigaria a mudar o backend
    # toda vez que a interface ganhasse um bloco novo. `NULL` = nunca arrumou,
    # então o frontend usa a disposição padrão dele.
    #
    # Diferente de `CorFormaPagamento`, esta preferência é por usuário: a
    # disposição da tela é de quem a arrumou, não do app inteiro.
    layout_dashboard: Mapped[str | None] = mapped_column(Text, nullable=True)


class Conta(Base):
    """Uma conta de verdade: Nubank, Mercado Pago, dinheiro em espécie.

    Cada conta guarda duas carteiras — o saldo disponível e a reserva. A reserva
    é por conta porque na prática ela mora em lugares diferentes: uma caixinha
    no Mercado Pago e um ETF no Nubank são reservas distintas, e somar as duas
    num número só esconderia onde o dinheiro está.

    Contas são globais, não por ano: o Nubank de 2026 é o mesmo de 2027, e isso
    permite comparar a evolução de cada conta ao longo dos anos.
    """

    __tablename__ = "contas"
    __table_args__ = (
        CheckConstraint(
            "dia_vencimento_fatura IS NULL OR dia_vencimento_fatura BETWEEN 1 AND 31",
            name="ck_conta_dia_vencimento_fatura",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    cor: Mapped[str] = mapped_column(String(7), nullable=False, default="#8d7799")
    # Controla a ordem de exibição; a conta principal fica em primeiro.
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tipo: Mapped[TipoConta] = mapped_column(
        Enum(TipoConta, native_enum=False), nullable=False, default=TipoConta.CORRENTE
    )
    # Só relevante para tipo=cartao_credito, abaixo.
    dia_vencimento_fatura: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conta_pagamento_padrao_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id", ondelete="SET NULL"), nullable=True
    )

    saldos: Mapped[list["SaldoInicial"]] = relationship(
        back_populates="conta", cascade="all, delete-orphan"
    )
    conta_pagamento_padrao: Mapped["Conta | None"] = relationship(
        remote_side=[id], foreign_keys=[conta_pagamento_padrao_id]
    )


class SaldoInicial(Base):
    """Quanto havia em uma conta antes do primeiro lançamento de um ano.

    Fica separado de `Conta` porque é um valor por ano: cada ano tem sua própria
    abertura, e arquivar um ano grava a abertura do seguinte.
    """

    __tablename__ = "saldos_iniciais"
    __table_args__ = (
        UniqueConstraint("ano_id", "conta_id", name="uq_saldo_inicial_ano_conta"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conta_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    saldo: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    guardado: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    conta: Mapped["Conta"] = relationship(back_populates="saldos")
    ano_ref: Mapped["Ano"] = relationship(back_populates="saldos_iniciais")


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
        UniqueConstraint("ano_id", "fitid", name="uq_lancamento_fitid_por_ano"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Em qual conta o dinheiro se moveu. Numa transferência, é a de origem.
    conta_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Só em transferências: para onde o dinheiro foi.
    conta_destino_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id", ondelete="RESTRICT"), nullable=True
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

    # Só faz sentido para saídas. Nulo é tratado como débito (ver ADR-0001) —
    # lançamentos antigos, sem o campo, continuam se comportando como sempre.
    forma_pagamento: Mapped[FormaPagamento | None] = mapped_column(
        Enum(FormaPagamento, native_enum=False), nullable=True
    )

    # Só faz sentido para saídas; os demais tipos não entram no gráfico por categoria.
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Identificador da transação no extrato do banco (FITID do OFX). Preenchido
    # só em lançamentos importados; é o que impede que reimportar o mesmo
    # extrato duplique tudo. Único por ano, não global: bancos diferentes podem
    # emitir o mesmo FITID.
    fitid: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    ano_ref: Mapped["Ano"] = relationship(back_populates="lancamentos")
    categoria: Mapped["Categoria | None"] = relationship(back_populates="lancamentos")
    conta: Mapped["Conta"] = relationship(foreign_keys=[conta_id])
    conta_destino: Mapped["Conta | None"] = relationship(
        foreign_keys=[conta_destino_id]
    )


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
    # Texto livre digitado antes do enum existir (ex.: "boleto", "débito
    # automático"). Mantido só para exibição do que já estava escrito — nenhuma
    # regra nova lê este campo. Ver spec "Forma de pagamento".
    forma_pagamento_legado: Mapped[str] = mapped_column(
        String(60), nullable=False, default=""
    )
    forma_pagamento: Mapped[FormaPagamento | None] = mapped_column(
        Enum(FormaPagamento, native_enum=False), nullable=True
    )
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True
    )
    # De qual conta a despesa sai; herdada pelo lançamento gerado a cada mês.
    conta_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False, index=True
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


class RegraCategorizacao(Base):
    """Regra que sugere categoria a partir da descrição do extrato.

    O usuário ensina uma vez ("iFood é Comida") e as importações seguintes já
    chegam categorizadas. As regras são globais, como as categorias, para
    valerem em todos os anos.

    A sugestão nunca é aplicada sozinha: ela preenche a tela de revisão, e quem
    confirma é o usuário.
    """

    __tablename__ = "regras_categorizacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Trecho procurado na descrição, sem acento e em maiúsculas — a comparação
    # é feita sobre a descrição normalizada da mesma forma.
    padrao: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    categoria: Mapped["Categoria"] = relationship()


class CorFormaPagamento(Base):
    """Cor de exibição de cada forma de pagamento (débito, crédito, pix,
    dinheiro), puramente cosmética.

    Fica no banco — não no navegador — de propósito: a usuária usa o app tanto
    no celular quanto no PC, e uma preferência salva só em `localStorage` não
    apareceria igual nos dois. Global, como `Categoria.cor`: as quatro formas
    de pagamento são fixas para o app inteiro, não por ano nem por usuário.

    Uma linha só existe aqui depois que a usuária troca a cor pela primeira
    vez; antes disso, o padrão vem do código (ver `app/routers/preferencias.py`).
    """

    __tablename__ = "cores_forma_pagamento"

    forma_pagamento: Mapped[FormaPagamento] = mapped_column(
        Enum(FormaPagamento, native_enum=False), primary_key=True
    )
    cor: Mapped[str] = mapped_column(String(7), nullable=False)


class FaturaMensal(Base):
    """Situação da fatura de um cartão em um mês específico (pago/pendente).

    Molde de `GastoFixoMensal`, mas precisa de `ano_id` próprio — diferente de
    um gasto fixo, o cartão (como a conta) é global e existe em todos os anos,
    então não há um `ano_id` para pegar emprestado.
    """

    __tablename__ = "faturas_mensais"
    __table_args__ = (
        UniqueConstraint(
            "cartao_id", "ano_id", "mes", name="uq_fatura_cartao_ano_mes"
        ),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_fatura_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cartao_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    situacao: Mapped[SituacaoGastoFixo] = mapped_column(
        Enum(SituacaoGastoFixo, native_enum=False),
        nullable=False,
        default=SituacaoGastoFixo.PENDENTE,
    )
    # Preenchido quando a fatura vira uma transferência de verdade.
    lancamento_id: Mapped[int | None] = mapped_column(
        ForeignKey("lancamentos.id", ondelete="SET NULL"), nullable=True
    )


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
