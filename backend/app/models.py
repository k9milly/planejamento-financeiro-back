"""Modelos ORM do Planejamento Financeiro.

O domínio gira em torno de duas "carteiras": a **conta** (dinheiro disponível no
dia a dia) e o **guardado** (a reserva). Todo lançamento afeta uma delas, as
duas, ou move dinheiro entre elas — ver `TipoLancamento`.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

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
    false,
    func,
    true,
)
from sqlalchemy.orm import (
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
)

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
    TRANSFERENCIA_CAIXINHA  nenhum efeito nas carteiras da conta

    PERDA existe porque investimento cai. Sem ela, uma queda do ETF teria de ser
    lançada como saída, e apareceria como gasto no relatório por categoria —
    dinheiro que encolheu não é dinheiro que foi consumido.

    TRANSFERENCIA existe porque mover dinheiro entre contas suas não é receita
    nem despesa. Lançar como saída em uma e entrada na outra inflaria os dois
    totais do mês sem que nada tivesse sido gasto ou recebido.

    TRANSFERENCIA_CAIXINHA move dinheiro entre duas caixinhas da mesma conta
    (ADR-10). É o único tipo que não mexe em carteira nenhuma: o dinheiro
    continua guardado na mesma conta, só troca de rótulo. Existe como
    lançamento — em vez de uma edição silenciosa de saldo — para a realocação
    aparecer no histórico como qualquer outra movimentação.
    """

    ENTRADA = "entrada"
    SAIDA = "saida"
    GUARDADO = "guardado"
    RETIRADO = "retirado"
    RENDIMENTO = "rendimento"
    PERDA = "perda"
    TRANSFERENCIA = "transferencia"
    TRANSFERENCIA_CAIXINHA = "transferencia_caixinha"


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


class ModoJuros(str, enum.Enum):
    """Como a pessoa informou os juros de uma compra parcelada (ADR-14).

    `VALOR` é o número que o próprio cartão já mostra ("10x de R$ 105,32") —
    sem conta financeira nenhuma, só multiplicação, e por isso exato.
    `PERCENTUAL` é a taxa ao mês, com o sistema calculando por juros simples.
    """

    VALOR = "valor"
    PERCENTUAL = "percentual"


class TipoMetaPoupanca(str, enum.Enum):
    """As duas formas de querer poupar, que respondem a perguntas diferentes.

    `MENSAL` é um hábito ("guardar R$ 500 todo mês") e se compara ao guardado
    de cada mês. `PRAZO` é um objetivo ("juntar R$ 6.000 até dezembro") e se
    compara ao guardado acumulado. As duas podem estar ativas ao mesmo tempo
    (ADR-06).
    """

    MENSAL = "mensal"
    PRAZO = "prazo"


class PapelMembro(str, enum.Enum):
    """O que distingue quem administra o espaço de quem só o usa (ADR-15).

    **Os dois veem e editam o mesmo dinheiro.** A diferença é só
    administrativa: convidar, remover membro, renomear e apagar o espaço. É
    deliberado — o caso real que motivou isto é um casal dividindo o controle
    financeiro, e "membro só lê" resolveria um problema que ninguém tem, ao
    custo de uma permissão a mais para errar.
    """

    DONO = "dono"
    MEMBRO = "membro"


class Espaco(Base):
    """A unidade de isolamento de dados — não o usuário (ADR-15).

    Isolar por pessoa não modelaria "duas pessoas, os mesmos dados" sem
    duplicar cada lançamento, o que quebraria a ideia de ser a mesma
    informação. Um espaço tem uma ou várias pessoas dentro; tudo o que é
    dinheiro pertence a um espaço.
    """

    __tablename__ = "espacos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    membros: Mapped[list["MembroEspaco"]] = relationship(
        back_populates="espaco", cascade="all, delete-orphan"
    )


class MembroEspaco(Base):
    """Quem participa de qual espaço, e em que papel."""

    __tablename__ = "membros_espaco"
    __table_args__ = (
        UniqueConstraint("espaco_id", "usuario_id", name="uq_membro_espaco_usuario"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    espaco_id: Mapped[int] = mapped_column(
        ForeignKey("espacos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    papel: Mapped[PapelMembro] = mapped_column(
        Enum(PapelMembro, native_enum=False), nullable=False
    )
    entrou_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    espaco: Mapped["Espaco"] = relationship(back_populates="membros")
    usuario: Mapped["Usuario"] = relationship(
        back_populates="participacoes", foreign_keys=[usuario_id]
    )


class ComEspaco:
    """Mixin: esta tabela guarda dinheiro, logo pertence a um espaço.

    Herdar deste mixin é o **único** jeito de uma tabela entrar no isolamento
    — `app/espaco.py` descobre os modelos protegidos percorrendo quem herda
    daqui, em vez de manter uma lista à parte. A diferença importa: uma lista
    é algo que alguém precisa lembrar de atualizar ao criar a décima quinta
    tabela, e esquecer significa vazar dinheiro de uma família para outra.
    Herdando, a tabela nova ou está protegida ou nem compila.

    `CASCADE`: apagar um espaço apaga o que havia dentro dele. É o que o
    direito ao esquecimento pede, e o motivo de `DELETE /auth/eu` poder ser
    uma exclusão de verdade em vez de um soft-delete.
    """

    @declared_attr
    def espaco_id(cls) -> Mapped[int]:
        return mapped_column(
            ForeignKey("espacos.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class Ano(Base, ComEspaco):
    """Um ano-calendário de planejamento, com seus 12 meses.

    Ao arquivar um ano ele fica somente-leitura, mas continua acessível — é a
    "pasta" de anos anteriores que o usuário consulta quando quiser.
    """

    __tablename__ = "anos"
    __table_args__ = (
        # Era `unique=True` global. Dois espaços precisam poder ter 2026 cada
        # um — é literalmente o primeiro passo do teste de isolamento.
        UniqueConstraint("espaco_id", "ano", name="uq_ano_por_espaco"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)

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

    # Como a pessoa quer ser chamada na interface. Opcional: quem nunca
    # preencheu continua identificado pelo e-mail, como era antes (ADR-06).
    nome: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Se os alertas de vencimento também devem sair por e-mail, além de
    # aparecerem no app. Nasce desligado, e por enquanto ligá-lo não faz nada:
    # o backend não envia e-mail nenhum — não existe serviço de envio nem
    # processo agendado. O campo existe para a preferência ter onde morar
    # quando essa fase chegar (ADR-06, seção 4).
    alertas_email_ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Se a seção de orçamento por categoria aparece na tela (ADR-11). Nasce
    # ligada: quem cadastrou um limite quer vê-lo, e quem não cadastrou não vê
    # seção nenhuma de qualquer forma — a lista sai vazia.
    #
    # Desligar não apaga nenhum `Categoria.limite_mensal`: é só uma preferência
    # de exibição. Fica no banco, e não no `localStorage`, porque a usuária
    # abre o app instalado num aparelho e pelo navegador em outro — a
    # preferência segue a conta, não o dispositivo (mesmo motivo de
    # `alertas_email_ativo`).
    mostrar_orcamento_categoria: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # Qual espaço esta pessoa está vendo agora — como um seletor de área de
    # trabalho. Fica no banco, e não no navegador, pelo mesmo motivo das outras
    # preferências (ADR-11): ela abre de outro aparelho e deve continuar no
    # mesmo lugar.
    #
    # `SET NULL`: apagar um espaço não pode apagar quem participava dele.
    # Nulo significa "ainda não escolheu", e nesse estado nenhuma consulta de
    # dado financeiro devolve nada — ver `app/espaco.py`.
    espaco_atual_id: Mapped[int | None] = mapped_column(
        ForeignKey("espacos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    espaco_atual: Mapped["Espaco | None"] = relationship(
        foreign_keys=[espaco_atual_id]
    )

    # Os espaços de que esta pessoa participa. `foreign_keys` é obrigatório
    # aqui: `membros_espaco` aponta para `usuarios` e `usuarios` aponta para
    # `espacos`, e sem dizer por qual caminho ir o SQLAlchemy não tem como
    # escolher.
    participacoes: Mapped[list["MembroEspaco"]] = relationship(
        back_populates="usuario",
        cascade="all, delete-orphan",
        foreign_keys="MembroEspaco.usuario_id",
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


class Conta(Base, ComEspaco):
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
        # Era global: duas famílias não conseguiriam ter um "Nubank" cada.
        UniqueConstraint("espaco_id", "nome", name="uq_conta_por_espaco"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), nullable=False)
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


class SaldoInicial(Base, ComEspaco):
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
    saldo: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    guardado: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    conta: Mapped["Conta"] = relationship(back_populates="saldos")
    ano_ref: Mapped["Ano"] = relationship(back_populates="saldos_iniciais")


class Categoria(Base, ComEspaco):
    """Categoria de gasto. Global (não pertence a um ano) para que os relatórios
    por categoria possam ser comparados entre anos."""

    __tablename__ = "categorias"
    __table_args__ = (
        CheckConstraint(
            "limite_mensal IS NULL OR limite_mensal > 0",
            name="ck_categoria_limite_positivo",
        ),
        # Era global — e "Alimentação" nos dois espaços é o segundo passo do
        # teste de isolamento do ADR-15.
        UniqueConstraint("espaco_id", "nome", name="uq_categoria_por_espaco"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), nullable=False)
    cor: Mapped[str] = mapped_column(String(7), nullable=False, default="#94a3b8")
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Quanto se pretende gastar nesta categoria por mês (ADR-11). Recorrente:
    # o mesmo valor todo mês, sem variar mês a mês nesta primeira versão.
    #
    # `None` é o normal, não uma pendência — a maioria das categorias não tem
    # orçamento, e continua sendo categoria de uso comum. Editar o limite vale
    # a partir da edição: o mês corrente recalcula a porcentagem na hora, sem
    # reescrever histórico, porque o número guardado é a intenção e não o
    # resultado.
    #
    # Isto reverte o ADR-0007, que decidira rastrear só o que de fato
    # aconteceu. O gasto real por categoria não muda em nada — já vinha de
    # `gastos_por_categoria`; o que passou a existir é o outro lado da conta.
    limite_mensal: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    lancamentos: Mapped[list["Lancamento"]] = relationship(back_populates="categoria")


class Lancamento(Base, ComEspaco):
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
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
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

    # Em qual caixinha da reserva o dinheiro entrou ou de qual saiu (ADR-10).
    # Nulo é o comportamento de sempre: entra no guardado da conta sem rótulo.
    # Numa transferência entre caixinhas, é a de origem.
    caixinha_id: Mapped[int | None] = mapped_column(
        ForeignKey("caixinhas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Só em TRANSFERENCIA_CAIXINHA: para qual caixinha o dinheiro foi.
    caixinha_destino_id: Mapped[int | None] = mapped_column(
        ForeignKey("caixinhas.id", ondelete="RESTRICT"), nullable=True
    )

    # De qual compra parcelada esta linha é uma parcela (ADR-14). Nulo em todo
    # lançamento comum, que é a esmagadora maioria.
    #
    # `CASCADE` aqui é intencional e diferente do `RESTRICT` das caixinhas:
    # apagar a compra é a ação "desfazer a compra inteira", e as parcelas só
    # existem por causa dela. Apagar **uma** parcela continua sendo o
    # `DELETE /anos/{ano}/lancamentos/{id}` de sempre.
    compra_parcelada_id: Mapped[int | None] = mapped_column(
        ForeignKey("compras_parceladas.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Qual parcela esta é, começando em 1 — o "3" de "3/10".
    numero_parcela: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
    caixinha: Mapped["Caixinha | None"] = relationship(foreign_keys=[caixinha_id])
    caixinha_destino: Mapped["Caixinha | None"] = relationship(
        foreign_keys=[caixinha_destino_id]
    )


class GastoFixo(Base, ComEspaco):
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
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
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


class GastoFixoMensal(Base, ComEspaco):
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


class RegraCategorizacao(Base, ComEspaco):
    """Regra que sugere categoria a partir da descrição do extrato.

    O usuário ensina uma vez ("iFood é Comida") e as importações seguintes já
    chegam categorizadas. As regras são globais, como as categorias, para
    valerem em todos os anos.

    A sugestão nunca é aplicada sozinha: ela preenche a tela de revisão, e quem
    confirma é o usuário.
    """

    __tablename__ = "regras_categorizacao"
    __table_args__ = (
        # Era global: um espaço ensinar "IFOOD" impediria o outro de ensinar.
        UniqueConstraint("espaco_id", "padrao", name="uq_regra_por_espaco"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Trecho procurado na descrição, sem acento e em maiúsculas — a comparação
    # é feita sobre a descrição normalizada da mesma forma.
    padrao: Mapped[str] = mapped_column(String(120), nullable=False)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    categoria: Mapped["Categoria"] = relationship()


class CorFormaPagamento(Base, ComEspaco):
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

    # Chave primária composta com o espaço. Antes era só a forma de pagamento,
    # o que daria uma cor de "crédito" para o sistema inteiro: o primeiro
    # espaço a escolher uma cor impediria todos os outros de escolherem a sua.
    #
    # A coluna é redeclarada aqui, em vez de vir do mixin, só para entrar na
    # chave — a tabela continua herdando `ComEspaco`, e portanto continua
    # sendo descoberta pelo isolamento automático.
    espaco_id: Mapped[int] = mapped_column(
        ForeignKey('espacos.id', ondelete='CASCADE'), primary_key=True, index=True
    )
    forma_pagamento: Mapped[FormaPagamento] = mapped_column(
        Enum(FormaPagamento, native_enum=False), primary_key=True
    )
    cor: Mapped[str] = mapped_column(String(7), nullable=False)


class MetaPoupanca(Base, ComEspaco):
    """Quanto a pessoa quer guardar — por mês, ou até uma data (ADR-06).

    É uma entidade e não um campo solto no usuário porque tem ciclo de vida
    próprio: nasce, fica ativa, e é aposentada quando outra do mesmo tipo a
    substitui. Meta trocada não é apagada — vira `ativa=False` e some do
    progresso, mas continua no banco como histórico do que já se pretendeu.

    Global, como o resto do domínio financeiro (`Ano`, `Conta`, `Categoria`):
    quem é por usuário aqui é só a preferência de tela, não o dinheiro.

    **Várias metas do mesmo tipo podem estar ativas ao mesmo tempo** (ADR-13).
    O ADR-06 limitava a uma por tipo, porque meta era um hábito genérico
    ("guardar X por mês"); virou objetivo específico — juntar para um tênis e
    para um curso são duas metas, com progressos que não se somam.

    O progresso não é guardado em coluna nenhuma — é recalculado a partir do
    `guardado` que `services/calculos.py` já apura. Guardar um número
    derivado abriria a porta para ele divergir da fonte.
    """

    __tablename__ = "metas_poupanca"
    __table_args__ = (
        CheckConstraint("valor_alvo > 0", name="ck_meta_valor_positivo"),
        # A regra "prazo exige data, mensal não usa data" também é validada no
        # schema, para o erro chegar em português. Aqui é a rede de segurança
        # contra escrita que não passe pela API.
        CheckConstraint(
            "(tipo = 'PRAZO' AND data_alvo IS NOT NULL) OR "
            "(tipo = 'MENSAL' AND data_alvo IS NULL)",
            name="ck_meta_data_alvo_coerente",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoMetaPoupanca] = mapped_column(
        Enum(TipoMetaPoupanca, native_enum=False), nullable=False, index=True
    )

    # Rótulo livre, só para diferenciar metas do mesmo tipo (ADR-13). Opcional
    # porque quem tem uma meta só não precisa nomeá-la — a interface cai num
    # rótulo genérico, como sempre fez.
    nome: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Para qual item da wishlist esta meta está juntando dinheiro (ADR-13).
    # É a meta que aponta para o objetivo, seguindo o mesmo sentido de
    # `Caixinha.meta_id` (ADR-10): o mais específico aponta para o mais geral.
    #
    # `SET NULL` e não `CASCADE`: apagar o desejo não pode apagar a meta junto,
    # porque o dinheiro guardado continua guardado — só perde a etiqueta.
    #
    # A meta é global e o item pertence a um ano; o vínculo atravessa essa
    # fronteira de propósito, já que juntar dinheiro para uma compra não se
    # interrompe na virada do ano.
    wishlist_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("wishlist.id", ondelete="SET NULL"), nullable=True, index=True
    )

    valor_alvo: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Só para `tipo=PRAZO`; obrigatoriamente nulo em `MENSAL`.
    data_alvo: Mapped[date | None] = mapped_column(Date, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )


class Caixinha(Base, ComEspaco):
    """Uma divisão nomeada da reserva de uma conta (ADR-10).

    A Kamilly guarda dinheiro em caixinhas nomeadas dentro do banco — uma
    reserva geral, outra para juntar o valor da fatura. O sistema já somava um
    `guardado` por conta; a caixinha dá nome às partes desse total.

    O saldo de uma caixinha é sempre uma **fração** do que já está guardado na
    conta, nunca dinheiro novo. A soma das caixinhas ativas de uma conta não
    passa do guardado dela; a diferença é o "guardado sem caixinha" — o que
    existia antes deste ADR, ou o que ainda não foi organizado.

    **Não existe coluna `saldo`.** O saldo é derivado, como o progresso de
    `MetaPoupanca`: `saldo_inicial` mais o efeito dos lançamentos que apontam
    para esta caixinha (ver `services/caixinhas.py`). Uma coluna de saldo teria
    de ser corrigida a cada criação, edição e exclusão de lançamento, e a
    primeira que escapasse deixaria o número mentindo em silêncio. Derivar
    também faz a desativação funcionar sozinha: sem a caixinha na lista das
    ativas, o dinheiro dela volta a contar como "sem caixinha", sem precisar
    de nenhum acerto de contas.

    Vinculada a uma conta, e não solta, porque é assim que caixinha funciona
    nos bancos dela. Só em conta corrente: um cartão de crédito não tem
    reserva (ADR-0002), então uma caixinha ali nunca poderia ter dinheiro.
    """

    __tablename__ = "caixinhas"
    __table_args__ = (
        CheckConstraint("saldo_inicial >= 0", name="ck_caixinha_saldo_inicial"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(60), nullable=False)

    # Opcional: quando aponta para uma meta, o saldo desta caixinha passa a
    # alimentar o progresso dela em vez do guardado da conta inteira (ADR-10).
    # SET NULL porque desativar uma meta não deve derrubar a caixinha junto.
    meta_id: Mapped[int | None] = mapped_column(
        ForeignKey("metas_poupanca.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Quanto desta caixinha vem de dinheiro que já estava guardado antes de
    # ela existir. Serve para dar nome, retroativamente, ao que foi lançado
    # sem caixinha — sem isso seria preciso inventar um lançamento de
    # "guardado" que somaria de novo um dinheiro que a conta já tem.
    #
    # Editável depois da criação: não é histórico, é rótulo. Mudá-lo não mexe
    # em lançamento nenhum, e as mesmas validações da criação valem na edição
    # (não passar do guardado sem caixinha, não deixar a caixinha negativa).
    saldo_inicial: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )

    criada_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # Desativar é soft-delete, como em `MetaPoupanca`: os lançamentos que
    # apontam para ela continuam existindo, e o saldo volta a ser "guardado
    # sem caixinha".
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    conta: Mapped["Conta"] = relationship()
    meta: Mapped["MetaPoupanca | None"] = relationship()


class CompraParcelada(Base, ComEspaco):
    """Uma compra no crédito dividida em parcelas (ADR-14).

    É o **molde**, como `GastoFixo` é o molde do gasto fixo — mas com uma
    diferença que muda tudo: aqui as N parcelas nascem **todas de uma vez**, na
    criação. Um gasto fixo pode variar ou ser pulado num mês; uma parcela de
    cartão é dívida já assumida no ato da compra. Esconder as futuras até
    "confirmar" cada uma esconderia um compromisso que já existe — o oposto do
    saldo inteligente que motivou o ADR-0002.

    Por isso nada aqui é somado por `services/calculos.py`: cada parcela é um
    `Lancamento` comum, e a fatura continua sendo a soma dos lançamentos de
    crédito, como sempre foi (ADR-0003).

    Não tem `ano_id`: as parcelas atravessam anos, e cada uma carrega o seu.
    """

    __tablename__ = "compras_parceladas"
    __table_args__ = (
        # Teto de 24: cobre o uso comum de cartão brasileiro e evita que um
        # erro de digitação ("240" no lugar de "24") gere centenas de
        # lançamentos e anos criados por engano.
        CheckConstraint(
            "numero_parcelas BETWEEN 2 AND 24", name="ck_compra_parcelada_numero"
        ),
        CheckConstraint("valor_parcela > 0", name="ck_compra_parcelada_valor_parcela"),
        CheckConstraint("valor_total > 0", name="ck_compra_parcelada_valor_total"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    descricao: Mapped[str] = mapped_column(String(120), nullable=False)
    conta_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True
    )
    numero_parcelas: Mapped[int] = mapped_column(Integer, nullable=False)

    tem_juros: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    modo_juros: Mapped[ModoJuros | None] = mapped_column(
        Enum(ModoJuros, native_enum=False), nullable=True
    )
    # Só no modo percentual. Guardado para a tela poder mostrar como o número
    # foi obtido — o cálculo em si já está congelado em `valor_parcela`.
    taxa_juros_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # O valor de cada parcela, já calculado. Quando a divisão não é exata, a
    # última parcela é maior — ela absorve os centavos que sobram, e por isso
    # este campo é "o valor da parcela comum", não necessariamente o de todas.
    valor_parcela: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # A soma efetiva das parcelas — **com** juros, quando houver. Não é o preço
    # à vista que a pessoa digitou no modo percentual.
    valor_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    criada_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    conta: Mapped["Conta"] = relationship()
    categoria: Mapped["Categoria | None"] = relationship()


class FaturaMensal(Base, ComEspaco):
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


class ItemWishlist(Base, ComEspaco):
    """Desejo de compra. Não afeta saldo — serve para planejar o uso da reserva."""

    __tablename__ = "wishlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    desejo: Mapped[str] = mapped_column(String(120), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    importancia: Mapped[Importancia] = mapped_column(
        Enum(Importancia, native_enum=False), nullable=False, default=Importancia.MEDIA
    )
    # Equivale à coluna "SOMAR" da planilha: só os marcados entram no total.
    somar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comprado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ano_ref: Mapped["Ano"] = relationship(back_populates="desejos")
