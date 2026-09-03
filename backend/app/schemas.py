"""Schemas Pydantic: o contrato da API.

Os tipos aqui são a fonte da verdade do que a API expõe. O frontend vive em
outro repositório e escreve os tipos dele à mão a partir de
`docs/CONTRATO-API.md` — então **mudar um campo aqui só está completo depois
de atualizar aquele documento**, senão o outro lado implementa contra uma
versão que não existe mais.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    DestinoRendimento,
    FormaPagamento,
    Importancia,
    SituacaoGastoFixo,
    TipoConta,
    TipoLancamento,
    TipoMetaPoupanca,
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
    # Caixinha da reserva envolvida (ADR-10). Opcional: sem ela, o guardado
    # entra na conta sem rótulo, exatamente como antes deste campo existir.
    caixinha_id: int | None = None
    caixinha_destino_id: int | None = None
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
            caixinha_id=self.caixinha_id,
            caixinha_destino_id=self.caixinha_destino_id,
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
    *,
    caixinha_id: int | None = None,
    caixinha_destino_id: int | None = None,
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

    _validar_caixinhas(tipo, destino, caixinha_id, caixinha_destino_id, erro)


# Onde uma caixinha faz sentido: nos tipos que mexem na reserva. Rendimento e
# perda entram só quando atingem o guardado — se o rendimento caiu na conta
# corrente, não há caixinha envolvida (ADR-10).
TIPOS_COM_CAIXINHA = {
    TipoLancamento.GUARDADO,
    TipoLancamento.RETIRADO,
    TipoLancamento.TRANSFERENCIA_CAIXINHA,
}


def mexe_na_reserva(
    tipo: TipoLancamento, destino: DestinoRendimento | None
) -> bool:
    """Se este lançamento tira ou põe dinheiro no `guardado` da conta.

    É a pergunta que decide se uma caixinha faz sentido — e, quando a conta
    tem caixinhas, se ela é obrigatória (ADR-10). Fica aqui, junto das outras
    regras de coerência, para os três caminhos que criam lançamento
    (cadastro, edição e importação) fazerem a mesma pergunta.
    """
    return tipo in TIPOS_COM_CAIXINHA or (
        tipo in TIPOS_COM_DESTINO and destino is DestinoRendimento.GUARDADO
    )


def _validar_caixinhas(
    tipo: TipoLancamento,
    destino: DestinoRendimento | None,
    caixinha_id: int | None,
    caixinha_destino_id: int | None,
    erro,
) -> None:
    """Quando `caixinha_id` e `caixinha_destino_id` são aceitos (ADR-10).

    Não checa aqui se a caixinha pertence à conta do lançamento nem se está
    ativa — isso depende de olhar o banco, e quem faz é o router.
    """
    if tipo is TipoLancamento.TRANSFERENCIA_CAIXINHA:
        if caixinha_id is None or caixinha_destino_id is None:
            raise erro(
                "Transferência entre caixinhas exige a caixinha de origem e a "
                "de destino."
            )
        if caixinha_id == caixinha_destino_id:
            raise erro("A caixinha de destino precisa ser diferente da de origem.")
        return

    if caixinha_destino_id is not None:
        raise erro(
            "'caixinha_destino_id' só se aplica a transferências entre caixinhas."
        )

    if caixinha_id is None:
        return

    if not mexe_na_reserva(tipo, destino):
        raise erro(
            "'caixinha_id' só se aplica a lançamentos que mexem na reserva: "
            "guardado, retirado, ou rendimento/perda com destino 'guardado'."
        )


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
    caixinha_id: int | None = None
    caixinha_destino_id: int | None = None
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
    caixinha_id: int | None
    caixinha_destino_id: int | None
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
    # Nem caixinha: o extrato não sabe que elas existem. Mas se a pessoa
    # marcar uma linha como `guardado` na revisão, a mesma regra do cadastro
    # manual vale — conta com caixinhas exige escolher uma (ADR-10).
    caixinha_id: int | None = None
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


# --------------------------------------------------------------------------- #
# Metas de poupança e alertas (ADR-06)
# --------------------------------------------------------------------------- #
class MetaPoupancaCriar(BaseModel):
    tipo: TipoMetaPoupanca
    valor_alvo: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    data_alvo: date | None = None

    @model_validator(mode="after")
    def _coerencia_do_tipo(self) -> "MetaPoupancaCriar":
        """Uma meta com prazo sem data não tem contra o que medir; uma meta
        mensal com data sugere um prazo que ela não respeita."""
        if self.tipo is TipoMetaPoupanca.PRAZO and self.data_alvo is None:
            raise ValueError("Uma meta com prazo precisa de uma data-alvo.")
        if self.tipo is TipoMetaPoupanca.MENSAL and self.data_alvo is not None:
            raise ValueError("Uma meta mensal não tem data-alvo.")
        return self


class MetaPoupancaOut(_Base):
    id: int
    tipo: TipoMetaPoupanca
    valor_alvo: Decimal
    data_alvo: date | None
    criada_em: datetime
    ativa: bool


class ProgressoMetaMensalOut(BaseModel):
    """Quanto do alvo do mês corrente já foi guardado."""

    id: int
    valor_alvo: Decimal
    guardado_no_mes: Decimal
    # Pode passar de 100 quando se guarda mais que o alvo — não é limitado de
    # propósito: bater 130% da meta é informação, não erro.
    percentual: float


class ProgressoMetaPrazoOut(BaseModel):
    """Quanto do alvo já foi acumulado, e quanto tempo resta."""

    id: int
    valor_alvo: Decimal
    data_alvo: date
    guardado_acumulado: Decimal
    percentual: float
    # Negativo quando a data já passou e a meta segue ativa — a interface
    # decide como mostrar isso; o backend não esconde o atraso.
    dias_restantes: int


class MetasAtivasOut(BaseModel):
    """As duas metas que podem estar valendo ao mesmo tempo, com o progresso
    já calculado. `null` no lugar de uma delas = não existe meta ativa
    daquele tipo."""

    mensal: ProgressoMetaMensalOut | None
    prazo: ProgressoMetaPrazoOut | None


class AlertaGastoFixoOut(BaseModel):
    """Um gasto fixo a vencer e ainda não pago."""

    tipo: Literal["gasto_fixo"] = "gasto_fixo"
    gasto_fixo_id: int
    nome: str
    dia_vencimento: int
    # 0 = vence hoje. Nunca negativo: vencido não entra na janela (ver router).
    dias_restantes: int
    valor: Decimal


class AlertaFaturaOut(BaseModel):
    """Uma fatura de cartão a vencer e ainda não paga."""

    tipo: Literal["fatura"] = "fatura"
    cartao_id: int
    nome_cartao: str
    dia_vencimento_fatura: int
    dias_restantes: int
    # O valor em aberto do mês, recalculado — mesma conta que
    # `GET .../fatura/{mes}` devolve. Nunca nulo: uma fatura sem valor em
    # aberto não vira alerta (ver `routers/alertas.py`).
    valor: Decimal


# União discriminada por `tipo`: os dois formatos têm campos com nomes
# diferentes de propósito. `dia_vencimento` (do gasto fixo) e
# `dia_vencimento_fatura` (do cartão) são coisas distintas em todo o resto da
# API — achatar os dois num nome só aqui criaria um vocabulário que só vale
# nesta rota. Idem `nome` e `nome_cartao`.
AlertaOut = Annotated[
    AlertaGastoFixoOut | AlertaFaturaOut, Field(discriminator="tipo")
]


# --------------------------------------------------------------------------- #
# Caixinhas (ADR-10)
# --------------------------------------------------------------------------- #
class CaixinhaCriar(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    meta_id: int | None = None
    # Dinheiro que já estava guardado nesta caixinha antes de ela existir no
    # sistema. O teto é o "guardado sem caixinha" da conta, checado no router
    # — aqui só se garante que não é negativo.
    saldo_inicial: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )


class CaixinhaAtualizar(BaseModel):
    """`saldo_inicial` não está aqui de propósito.

    Ele é a fotografia do que existia na criação; mudá-lo depois reescreveria
    o passado da caixinha sem nenhum lançamento explicando a diferença. Para
    corrigir o valor, o caminho é lançar (guardado/retirado) ou transferir.
    """

    nome: str | None = Field(default=None, min_length=1, max_length=60)
    # `None` explícito desvincula a meta — por isso o PATCH usa
    # `exclude_unset`: campo ausente e campo nulo querem dizer coisas
    # diferentes aqui.
    meta_id: int | None = None


class CaixinhaOut(_Base):
    id: int
    conta_id: int
    nome: str
    meta_id: int | None
    # Derivado, não é coluna: `saldo_inicial` mais o efeito dos lançamentos que
    # apontam para esta caixinha (ver `services/caixinhas.py`).
    saldo: Decimal
    criada_em: datetime
    ativa: bool


class TransferenciaCaixinha(BaseModel):
    caixinha_origem_id: int
    caixinha_destino_id: int
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
