"""Testes das regras de totalização.

Usam objetos simples em vez do ORM: as regras são puras e não precisam de banco.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.models import DestinoRendimento, TipoLancamento
from app.services.calculos import calcular_ano, calcular_totais_mes


@dataclass
class CategoriaFake:
    nome: str


@dataclass
class LancamentoFake:
    mes: int
    valor: Decimal
    tipo: TipoLancamento
    destino: DestinoRendimento | None = None
    categoria: CategoriaFake | None = None
    data: date = date(2026, 1, 1)


def _l(mes, valor, tipo, destino=None, categoria=None):
    return LancamentoFake(
        mes=mes,
        valor=Decimal(str(valor)),
        tipo=tipo,
        destino=destino,
        categoria=CategoriaFake(categoria) if categoria else None,
    )


D = Decimal


class TestTotaisMes:
    def test_entrada_aumenta_saldo(self):
        t = calcular_totais_mes(1, [_l(1, 100, TipoLancamento.ENTRADA)], D("0"), D("0"))
        assert t.entradas == D("100.00")
        assert t.saldo == D("100.00")
        assert t.guardado_acumulado == D("0")

    def test_saida_reduz_saldo_e_entra_na_categoria(self):
        t = calcular_totais_mes(
            1, [_l(1, 30, TipoLancamento.SAIDA, categoria="Comida")], D("100"), D("0")
        )
        assert t.saidas == D("30.00")
        assert t.saldo == D("70.00")
        assert t.gastos_por_categoria == {"Comida": D("30.00")}

    def test_guardar_move_da_conta_para_a_reserva(self):
        """O total do patrimônio não muda: só troca de carteira."""
        t = calcular_totais_mes(
            1, [_l(1, 200, TipoLancamento.GUARDADO)], D("500"), D("1000")
        )
        assert t.saldo == D("300.00")
        assert t.guardado_acumulado == D("1200.00")
        assert t.saldo + t.guardado_acumulado == D("1500.00")

    def test_retirar_move_da_reserva_para_a_conta(self):
        t = calcular_totais_mes(
            1, [_l(1, 150, TipoLancamento.RETIRADO)], D("50"), D("1000")
        )
        assert t.saldo == D("200.00")
        assert t.guardado_acumulado == D("850.00")

    def test_rendimento_respeita_o_destino(self):
        na_conta = calcular_totais_mes(
            1,
            [_l(1, 10, TipoLancamento.RENDIMENTO, DestinoRendimento.CONTA)],
            D("0"),
            D("0"),
        )
        assert na_conta.saldo == D("10.00")
        assert na_conta.guardado_acumulado == D("0")

        no_guardado = calcular_totais_mes(
            1,
            [_l(1, 10, TipoLancamento.RENDIMENTO, DestinoRendimento.GUARDADO)],
            D("0"),
            D("0"),
        )
        assert no_guardado.saldo == D("0")
        assert no_guardado.guardado_acumulado == D("10.00")

    def test_saida_sem_categoria_vai_para_grupo_proprio(self):
        """A planilha original tinha 3 saídas sem categoria; elas não podem
        simplesmente sumir do relatório."""
        t = calcular_totais_mes(1, [_l(1, 25, TipoLancamento.SAIDA)], D("0"), D("0"))
        assert t.gastos_por_categoria == {"Sem categoria": D("25.00")}

    def test_categorias_saem_ordenadas_por_valor(self):
        t = calcular_totais_mes(
            1,
            [
                _l(1, 10, TipoLancamento.SAIDA, categoria="Lazer"),
                _l(1, 90, TipoLancamento.SAIDA, categoria="Comida"),
                _l(1, 50, TipoLancamento.SAIDA, categoria="Transporte"),
            ],
            D("0"),
            D("0"),
        )
        assert list(t.gastos_por_categoria) == ["Comida", "Transporte", "Lazer"]


class TestCalcularAno:
    def test_devolve_sempre_doze_meses(self):
        meses = calcular_ano([], D("0"), D("0"))
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
            D("0"),
            D("0"),
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
            D("2000"),
            D("1000"),
        )
        assert meses[0].guardado_acumulado == D("1300.00")
        assert meses[4].guardado_acumulado == D("1500.00")
        assert meses[8].guardado_acumulado == D("1400.00")
        assert meses[11].guardado_acumulado == D("1400.00")

    def test_saldos_iniciais_do_ano_sao_respeitados(self):
        meses = calcular_ano([], D("0.97"), D("7867.36"))
        assert meses[0].saldo_inicial == D("0.97")
        assert meses[11].saldo == D("0.97")
        assert meses[11].guardado_acumulado == D("7867.36")

    def test_rendimento_do_guardado_entra_no_total_guardado(self):
        """Na planilha, o SUMIF de rendimentos usava um rótulo inexistente e
        sempre retornava zero — os rendimentos nunca somavam na reserva."""
        meses = calcular_ano(
            [_l(3, 47.75, TipoLancamento.RENDIMENTO, DestinoRendimento.GUARDADO)],
            D("0"),
            D("1000"),
        )
        assert meses[2].guardado_no_mes == D("47.75")
        assert meses[11].guardado_acumulado == D("1047.75")


class TestPrecisao:
    def test_centavos_nao_acumulam_erro(self):
        """Com float, somar 0.1 dez vezes não dá 1.0. Com Decimal, dá."""
        meses = calcular_ano(
            [_l(1, "0.10", TipoLancamento.ENTRADA) for _ in range(10)], D("0"), D("0")
        )
        assert meses[0].saldo == D("1.00")

    @pytest.mark.parametrize("valor", ["0.01", "1234567.89", "999999.99"])
    def test_valores_extremos(self, valor):
        t = calcular_totais_mes(
            1, [_l(1, valor, TipoLancamento.ENTRADA)], D("0"), D("0")
        )
        assert t.saldo == D(valor)
