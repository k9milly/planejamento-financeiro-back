"""Testes do interpretador de mensagens rápidas do Telegram."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.services.telegram_parser import ErroInterpretacao, escolher_conta, interpretar

D = Decimal


class TestInterpretar:
    def test_exemplo_real_da_usuaria(self):
        """A mensagem que motivou o recurso, incluindo palavras soltas que não
        são nem descrição nem nome exato de conta."""
        r = interpretar("15 reais, brownie, cartao credito mercado pago")
        assert r.valor == D("15.00")
        assert r.descricao == "brownie"
        assert r.conta_pedida == "cartao credito mercado pago"

    def test_so_valor(self):
        r = interpretar("15")
        assert r.valor == D("15.00")
        assert r.descricao == ""
        assert r.conta_pedida is None

    def test_valor_e_descricao_sem_conta(self):
        r = interpretar("15, brownie")
        assert r.valor == D("15.00")
        assert r.descricao == "brownie"
        assert r.conta_pedida is None

    def test_valor_com_virgula_decimal_nao_confunde_separador_de_campo(self):
        """O caso que motivou ler o valor antes de dividir por vírgula: sem
        isso, '15,50' quebraria ao meio no primeiro separador."""
        r = interpretar("15,50, brownie, mercado pago")
        assert r.valor == D("15.50")
        assert r.descricao == "brownie"
        assert r.conta_pedida == "mercado pago"

    def test_valor_com_ponto_decimal(self):
        r = interpretar("15.50, brownie")
        assert r.valor == D("15.50")

    def test_palavra_reais_e_descartada(self):
        assert interpretar("15 reais, brownie").descricao == "brownie"

    def test_r_cifrao_antes_do_numero_e_descartado(self):
        r = interpretar("R$ 15, brownie")
        assert r.valor == D("15.00")
        assert r.descricao == "brownie"

    def test_r_cifrao_minusculo_tambem_funciona(self):
        assert interpretar("r$15, brownie").valor == D("15.00")

    def test_espacos_extras_sao_ignorados(self):
        r = interpretar("  15  ,   brownie  ,  mercado pago  ")
        assert r.descricao == "brownie"
        assert r.conta_pedida == "mercado pago"

    def test_terceira_virgula_fica_dentro_da_conta(self):
        """Só a primeira vírgula depois da descrição separa campos; o resto
        do texto (por mais vírgulas que tenha) é um campo só."""
        r = interpretar("15, brownie, mercado pago, credito")
        assert r.conta_pedida == "mercado pago, credito"

    def test_mensagem_vazia_e_recusada(self):
        with pytest.raises(ErroInterpretacao):
            interpretar("")
        with pytest.raises(ErroInterpretacao):
            interpretar("   ")

    def test_sem_valor_no_inicio_e_recusado(self):
        with pytest.raises(ErroInterpretacao):
            interpretar("brownie, 15, mercado pago")

    def test_valor_zero_e_recusado(self):
        with pytest.raises(ErroInterpretacao):
            interpretar("0, brownie")

    def test_valor_negativo_nao_e_reconhecido_como_valor(self):
        """O regex não inclui o sinal de menos: '-15' não casa como número no
        início, então vira erro de formato — não um valor negativo aceito."""
        with pytest.raises(ErroInterpretacao):
            interpretar("-15, brownie")


@dataclass
class _ContaFake:
    nome: str


class TestEscolherConta:
    def setup_method(self):
        self.mercado_pago = _ContaFake("Mercado Pago")
        self.nubank = _ContaFake("Nubank")
        self.contas = [self.mercado_pago, self.nubank]

    def test_sem_pedido_usa_a_padrao(self):
        conta, aviso = escolher_conta(None, self.contas, self.mercado_pago)
        assert conta is self.mercado_pago
        assert aviso is None

    def test_reconhece_por_trecho_com_texto_ao_redor(self):
        conta, aviso = escolher_conta(
            "cartao credito mercado pago", self.contas, self.mercado_pago
        )
        assert conta is self.mercado_pago
        assert aviso is None

    def test_reconhece_ignorando_acento_e_caixa(self):
        conta, _ = escolher_conta("NUBANK", self.contas, self.mercado_pago)
        assert conta is self.nubank

    def test_pedido_nao_reconhecido_cai_no_padrao_com_aviso(self):
        conta, aviso = escolher_conta("carteira", self.contas, self.mercado_pago)
        assert conta is self.mercado_pago
        assert aviso is not None
        assert "carteira" in aviso

    def test_nome_mais_especifico_vence_em_empate(self):
        """Uma conta cujo nome é substring do de outra não pode ganhar por
        acaso da ordem da lista."""
        mercado = _ContaFake("Mercado")
        mercado_pago = _ContaFake("Mercado Pago")
        conta, _ = escolher_conta(
            "mercado pago", [mercado, mercado_pago], mercado
        )
        assert conta is mercado_pago
