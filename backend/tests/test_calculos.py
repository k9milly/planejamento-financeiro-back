"""Testes das regras de totalização.

Usam objetos simples em vez do ORM: as regras são puras e não precisam de banco.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.models import DestinoRendimento, TipoConta, TipoLancamento
from app.services.calculos import Carteiras, calcular_ano, calcular_totais_mes

NUBANK = 1
MERCADO_PAGO = 2
CARTAO = 3


@dataclass
class CategoriaFake:
    nome: str


@dataclass
class LancamentoFake:
    mes: int
    valor: Decimal
    tipo: TipoLancamento
    conta_id: int = NUBANK
    conta_destino_id: int | None = None
    destino: DestinoRendimento | None = None
    categoria: CategoriaFake | None = None
    data: date = date(2026, 1, 1)


def _l(mes, valor, tipo, *, conta=NUBANK, destino_conta=None, destino=None,
       categoria=None):
    return LancamentoFake(
        mes=mes,
        valor=Decimal(str(valor)),
        tipo=tipo,
        conta_id=conta,
        conta_destino_id=destino_conta,
        destino=destino,
        categoria=CategoriaFake(categoria) if categoria else None,
    )


def _abertura(**contas: tuple[str, str]) -> dict[int, Carteiras]:
    """_abertura(**{'1': ('100', '0')}) -> {1: Carteiras(100, 0)}"""
    return {
        int(conta_id): Carteiras(saldo=Decimal(saldo), guardado=Decimal(guardado))
        for conta_id, (saldo, guardado) in contas.items()
    }


VAZIO: dict[int, Carteiras] = {}
D = Decimal


class TestTotaisMes:
    def test_entrada_aumenta_saldo(self):
        t = calcular_totais_mes(1, [_l(1, 100, TipoLancamento.ENTRADA)], VAZIO)
        assert t.entradas == D("100.00")
        assert t.saldo == D("100.00")
        assert t.guardado_acumulado == ZERO_DECIMAL

    def test_saida_reduz_saldo_e_entra_na_categoria(self):
        t = calcular_totais_mes(
            1,
            [_l(1, 30, TipoLancamento.SAIDA, categoria="Comida")],
            _abertura(**{"1": ("100", "0")}),
        )
        assert t.saidas == D("30.00")
        assert t.saldo == D("70.00")
        assert t.gastos_por_categoria == {"Comida": D("30.00")}

    def test_guardar_move_do_saldo_para_a_reserva(self):
        """O patrimônio não muda: só troca de carteira."""
        t = calcular_totais_mes(
            1,
            [_l(1, 200, TipoLancamento.GUARDADO)],
            _abertura(**{"1": ("500", "1000")}),
        )
        assert t.saldo == D("300.00")
        assert t.guardado_acumulado == D("1200.00")
        assert t.saldo + t.guardado_acumulado == D("1500.00")

    def test_retirar_move_da_reserva_para_o_saldo(self):
        t = calcular_totais_mes(
            1,
            [_l(1, 150, TipoLancamento.RETIRADO)],
            _abertura(**{"1": ("50", "1000")}),
        )
        assert t.saldo == D("200.00")
        assert t.guardado_acumulado == D("850.00")

    def test_rendimento_respeita_o_destino(self):
        na_conta = calcular_totais_mes(
            1,
            [_l(1, 10, TipoLancamento.RENDIMENTO, destino=DestinoRendimento.CONTA)],
            VAZIO,
        )
        assert na_conta.saldo == D("10.00")
        assert na_conta.guardado_acumulado == ZERO_DECIMAL

        no_guardado = calcular_totais_mes(
            1,
            [_l(1, 10, TipoLancamento.RENDIMENTO, destino=DestinoRendimento.GUARDADO)],
            VAZIO,
        )
        assert no_guardado.saldo == ZERO_DECIMAL
        assert no_guardado.guardado_acumulado == D("10.00")

    def test_saida_sem_categoria_vai_para_grupo_proprio(self):
        t = calcular_totais_mes(1, [_l(1, 25, TipoLancamento.SAIDA)], VAZIO)
        assert t.gastos_por_categoria == {"Sem categoria": D("25.00")}

    def test_categorias_saem_ordenadas_por_valor(self):
        t = calcular_totais_mes(
            1,
            [
                _l(1, 10, TipoLancamento.SAIDA, categoria="Lazer"),
                _l(1, 90, TipoLancamento.SAIDA, categoria="Comida"),
                _l(1, 50, TipoLancamento.SAIDA, categoria="Transporte"),
            ],
            VAZIO,
        )
        assert list(t.gastos_por_categoria) == ["Comida", "Transporte", "Lazer"]


class TestPerda:
    """Investimento cai, e isso não é um gasto."""

    def test_perda_no_guardado_reduz_a_reserva(self):
        t = calcular_totais_mes(
            1,
            [_l(1, 80, TipoLancamento.PERDA, destino=DestinoRendimento.GUARDADO)],
            _abertura(**{"1": ("0", "1000")}),
        )
        assert t.guardado_acumulado == D("920.00")

    def test_perda_nao_conta_como_saida(self):
        """Lançar desvalorização do ETF como saída faria o relatório dizer que
        você gastou um dinheiro que só encolheu."""
        t = calcular_totais_mes(
            1,
            [_l(1, 80, TipoLancamento.PERDA, destino=DestinoRendimento.GUARDADO)],
            _abertura(**{"1": ("0", "1000")}),
        )
        assert t.saidas == ZERO_DECIMAL
        assert t.gastos_por_categoria == {}
        assert t.perdas == D("80.00")

    def test_rendimento_e_perda_se_compensam(self):
        t = calcular_totais_mes(
            1,
            [
                _l(1, 100, TipoLancamento.RENDIMENTO,
                   destino=DestinoRendimento.GUARDADO),
                _l(1, 100, TipoLancamento.PERDA, destino=DestinoRendimento.GUARDADO),
            ],
            _abertura(**{"1": ("0", "1000")}),
        )
        assert t.guardado_acumulado == D("1000.00")


class TestTransferencia:
    """O caso que motivou o modelo de contas."""

    def test_move_dinheiro_entre_contas(self):
        t = calcular_totais_mes(
            1,
            [
                _l(1, 200, TipoLancamento.TRANSFERENCIA,
                   conta=NUBANK, destino_conta=MERCADO_PAGO)
            ],
            _abertura(**{"1": ("500", "0"), "2": ("100", "0")}),
        )
        assert t.por_conta[NUBANK].saldo == D("300.00")
        assert t.por_conta[MERCADO_PAGO].saldo == D("300.00")

    def test_nao_conta_como_entrada_nem_saida(self):
        """Antes do tipo transferência, mandar R$ 200 de uma conta sua para
        outra inflava saídas e entradas em R$ 200 sem nada ter sido gasto."""
        t = calcular_totais_mes(
            1,
            [
                _l(1, 200, TipoLancamento.TRANSFERENCIA,
                   conta=NUBANK, destino_conta=MERCADO_PAGO)
            ],
            _abertura(**{"1": ("500", "0"), "2": ("100", "0")}),
        )
        assert t.entradas == ZERO_DECIMAL
        assert t.saidas == ZERO_DECIMAL
        assert t.gastos_por_categoria == {}

    def test_patrimonio_total_nao_muda(self):
        abertura = _abertura(**{"1": ("500", "0"), "2": ("100", "0")})
        t = calcular_totais_mes(
            1,
            [
                _l(1, 200, TipoLancamento.TRANSFERENCIA,
                   conta=NUBANK, destino_conta=MERCADO_PAGO)
            ],
            abertura,
        )
        assert t.saldo == D("600.00")

    def test_transferencia_para_conta_nova_funciona(self):
        """A conta destino pode não ter saldo de abertura."""
        t = calcular_totais_mes(
            1,
            [
                _l(1, 50, TipoLancamento.TRANSFERENCIA,
                   conta=NUBANK, destino_conta=MERCADO_PAGO)
            ],
            _abertura(**{"1": ("500", "0")}),
        )
        assert t.por_conta[MERCADO_PAGO].saldo == D("50.00")


class TestVariasContas:
    def test_saldos_ficam_separados_por_conta(self):
        t = calcular_totais_mes(
            1,
            [
                _l(1, 100, TipoLancamento.ENTRADA, conta=NUBANK),
                _l(1, 30, TipoLancamento.SAIDA, conta=MERCADO_PAGO,
                   categoria="Comida"),
            ],
            _abertura(**{"1": ("0", "0"), "2": ("200", "0")}),
        )
        assert t.por_conta[NUBANK].saldo == D("100.00")
        assert t.por_conta[MERCADO_PAGO].saldo == D("170.00")
        assert t.saldo == D("270.00")

    def test_reserva_fica_separada_por_conta(self):
        """A caixinha do Mercado Pago e o ETF do Nubank são reservas distintas."""
        t = calcular_totais_mes(
            1,
            [
                _l(1, 50, TipoLancamento.RENDIMENTO, conta=MERCADO_PAGO,
                   destino=DestinoRendimento.GUARDADO),
                _l(1, 20, TipoLancamento.PERDA, conta=NUBANK,
                   destino=DestinoRendimento.GUARDADO),
            ],
            _abertura(**{"1": ("0", "1000"), "2": ("0", "5000")}),
        )
        assert t.por_conta[NUBANK].guardado == D("980.00")
        assert t.por_conta[MERCADO_PAGO].guardado == D("5050.00")
        assert t.guardado_acumulado == D("6030.00")


class TestSaldoInteligente:
    """Compra no crédito não pode descontar do saldo disponível (ADR-0002)."""

    TIPOS = {NUBANK: TipoConta.CORRENTE, CARTAO: TipoConta.CARTAO_CREDITO}

    def test_credito_nao_desconta_saldo_da_conta(self):
        t = calcular_totais_mes(
            1,
            [_l(1, 100, TipoLancamento.SAIDA, conta=CARTAO, categoria="Mercado")],
            _abertura(**{"1": ("500", "0")}),
            self.TIPOS,
        )
        assert t.saldo == D("500.00")
        assert t.por_cartao[CARTAO].saldo == D("-100.00")
        # A saída ainda entra nos totais do mês e no relatório por categoria —
        # só não sai do dinheiro disponível ainda.
        assert t.saidas == D("100.00")
        assert t.gastos_por_categoria == {"Mercado": D("100.00")}

    def test_debito_continua_descontando_normalmente(self):
        t = calcular_totais_mes(
            1,
            [_l(1, 100, TipoLancamento.SAIDA, conta=NUBANK, categoria="Mercado")],
            _abertura(**{"1": ("500", "0")}),
            self.TIPOS,
        )
        assert t.saldo == D("400.00")

    def test_pagar_fatura_e_uma_transferencia_da_conta_para_o_cartao(self):
        t = calcular_totais_mes(
            1,
            [
                _l(1, 100, TipoLancamento.SAIDA, conta=CARTAO),
                _l(1, 100, TipoLancamento.TRANSFERENCIA,
                   conta=NUBANK, destino_conta=CARTAO),
            ],
            _abertura(**{"1": ("500", "0")}),
            self.TIPOS,
        )
        assert t.saldo == D("400.00")  # dinheiro de verdade saiu da conta
        assert t.por_cartao[CARTAO].saldo == ZERO_DECIMAL  # dívida quitada

    def test_divida_do_cartao_encadeia_entre_meses(self):
        meses = calcular_ano(
            [_l(1, 300, TipoLancamento.SAIDA, conta=CARTAO)],
            _abertura(**{"1": ("1000", "0")}),
            self.TIPOS,
        )
        assert meses[0].por_cartao[CARTAO].saldo == D("-300.00")
        assert meses[1].por_cartao[CARTAO].saldo == D("-300.00")
        assert meses[11].saldo == D("1000.00")


class TestCalcularAno:
    def test_devolve_sempre_doze_meses(self):
        meses = calcular_ano([], VAZIO)
        assert len(meses) == 12
        assert [m.mes for m in meses] == list(range(1, 13))

    def test_saldo_encadeia_entre_meses(self):
        """Este é o comportamento que a planilha original não tinha: lá o saldo
        de abertura era digitado à mão em cada aba e desencontrava."""
        meses = calcular_ano(
            [
                _l(1, 1000, TipoLancamento.ENTRADA),
                _l(1, 400, TipoLancamento.SAIDA, categoria="Comida"),
                _l(2, 100, TipoLancamento.SAIDA, categoria="Lazer"),
            ],
            VAZIO,
        )
        assert meses[0].saldo == D("600.00")
        assert meses[1].saldo_inicial == D("600.00")
        assert meses[1].saldo == D("500.00")
        # Meses sem lançamento carregam o saldo adiante em vez de zerar.
        assert meses[11].saldo == D("500.00")

    def test_guardado_acumula_ao_longo_do_ano(self):
        meses = calcular_ano(
            [
                _l(1, 300, TipoLancamento.GUARDADO),
                _l(5, 200, TipoLancamento.GUARDADO),
                _l(9, 100, TipoLancamento.RETIRADO),
            ],
            _abertura(**{"1": ("2000", "1000")}),
        )
        assert meses[0].guardado_acumulado == D("1300.00")
        assert meses[4].guardado_acumulado == D("1500.00")
        assert meses[8].guardado_acumulado == D("1400.00")
        assert meses[11].guardado_acumulado == D("1400.00")

    def test_saldos_iniciais_do_ano_sao_respeitados(self):
        meses = calcular_ano([], _abertura(**{"1": ("0.97", "7867.36")}))
        assert meses[0].saldo_inicial == D("0.97")
        assert meses[11].saldo == D("0.97")
        assert meses[11].guardado_acumulado == D("7867.36")

    def test_transferencia_encadeia_nas_duas_contas(self):
        meses = calcular_ano(
            [
                _l(3, 500, TipoLancamento.TRANSFERENCIA,
                   conta=NUBANK, destino_conta=MERCADO_PAGO),
                _l(7, 100, TipoLancamento.SAIDA, conta=MERCADO_PAGO,
                   categoria="Comida"),
            ],
            _abertura(**{"1": ("1000", "0"), "2": ("0", "0")}),
        )
        assert meses[2].por_conta[NUBANK].saldo == D("500.00")
        assert meses[2].por_conta[MERCADO_PAGO].saldo == D("500.00")
        # O mês seguinte parte do fechamento, nas duas contas.
        assert meses[3].abertura_por_conta[MERCADO_PAGO].saldo == D("500.00")
        assert meses[6].por_conta[MERCADO_PAGO].saldo == D("400.00")
        assert meses[11].saldo == D("900.00")

    def test_guardado_no_mes_reflete_a_variacao(self):
        meses = calcular_ano(
            [_l(3, 47.75, TipoLancamento.RENDIMENTO,
                destino=DestinoRendimento.GUARDADO)],
            _abertura(**{"1": ("0", "1000")}),
        )
        assert meses[2].guardado_no_mes == D("47.75")
        assert meses[11].guardado_acumulado == D("1047.75")


class TestPrecisao:
    def test_centavos_nao_acumulam_erro(self):
        """Com float, somar 0.1 dez vezes não dá 1.0. Com Decimal, dá."""
        meses = calcular_ano(
            [_l(1, "0.10", TipoLancamento.ENTRADA) for _ in range(10)], VAZIO
        )
        assert meses[0].saldo == D("1.00")

    @pytest.mark.parametrize("valor", ["0.01", "1234567.89", "999999.99"])
    def test_valores_extremos(self, valor):
        t = calcular_totais_mes(1, [_l(1, valor, TipoLancamento.ENTRADA)], VAZIO)
        assert t.saldo == D(valor)


ZERO_DECIMAL = Decimal("0.00")
