"""Testes do leitor de OFX."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.ofx import ErroOFX, ler_ofx

# OFX 1.x: SGML, tags sem fechamento, cabeçalho de chave:valor. É o que o
# Nubank e a maioria dos bancos brasileiros exportam.
OFX_1X = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
CHARSET:1252

<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<CURDEF>BRL
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260805120000[-3:BRT]
<TRNAMT>-113.85
<FITID>abc-001
<MEMO>Compra no debito - CLAUDE AI
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260806
<TRNAMT>2000.00
<FITID>abc-002
<MEMO>Transferencia recebida
</STMTTRN>
</BANKTRANLIST>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
"""

# OFX 2.x: XML bem formado.
OFX_2X = b"""<?xml version="1.0" encoding="UTF-8"?>
<OFX>
  <BANKTRANLIST>
    <STMTTRN>
      <TRNTYPE>DEBIT</TRNTYPE>
      <DTPOSTED>20260810</DTPOSTED>
      <TRNAMT>-54.17</TRNAMT>
      <FITID>xyz-100</FITID>
      <NAME>INTERNET FIBRA</NAME>
    </STMTTRN>
  </BANKTRANLIST>
</OFX>
"""


class TestFormatos:
    def test_le_ofx_sgml(self):
        transacoes = ler_ofx(OFX_1X)
        assert len(transacoes) == 2

        saida = transacoes[0]
        assert saida.data == date(2026, 8, 5)
        assert saida.valor == Decimal("113.85")
        assert saida.saida is True
        assert saida.fitid == "abc-001"
        assert saida.descricao == "Compra no debito - CLAUDE AI"

    def test_le_ofx_xml(self):
        transacoes = ler_ofx(OFX_2X)
        assert len(transacoes) == 1
        # No XML as tags fecham; o valor não pode vir com o </TRNAMT> junto.
        assert transacoes[0].valor == Decimal("54.17")
        assert transacoes[0].descricao == "INTERNET FIBRA"

    def test_usa_name_quando_nao_ha_memo(self):
        assert ler_ofx(OFX_2X)[0].descricao == "INTERNET FIBRA"


class TestSinalEValor:
    def test_valor_negativo_vira_saida_positiva(self):
        """O sinal vira o tipo; o valor fica sempre positivo, como no resto do
        sistema."""
        saida = ler_ofx(OFX_1X)[0]
        assert saida.valor > 0
        assert saida.saida is True

    def test_valor_positivo_vira_entrada(self):
        entrada = ler_ofx(OFX_1X)[1]
        assert entrada.saida is False
        assert entrada.valor == Decimal("2000.00")

    def test_aceita_virgula_decimal(self):
        conteudo = OFX_2X.replace(b"-54.17", b"-54,17")
        assert ler_ofx(conteudo)[0].valor == Decimal("54.17")

    def test_ignora_valor_zero(self):
        conteudo = OFX_2X.replace(b"-54.17", b"0.00")
        assert ler_ofx(conteudo) == []


class TestRobustez:
    def test_arquivo_sem_transacoes_e_recusado(self):
        with pytest.raises(ErroOFX):
            ler_ofx(b"isto nao e um extrato")

    def test_ignora_transacao_sem_data(self):
        conteudo = OFX_2X.replace(b"<DTPOSTED>20260810</DTPOSTED>", b"")
        assert ler_ofx(conteudo) == []

    def test_le_acentos_em_latin1(self):
        """Bancos brasileiros exportam em ISO-8859-1, não UTF-8."""
        conteudo = OFX_1X.replace(
            b"Transferencia recebida", "Transferência recebida".encode("cp1252")
        )
        assert "Transferência recebida" in ler_ofx(conteudo)[1].descricao

    def test_sem_fitid_gera_identificador_estavel(self):
        conteudo = OFX_2X.replace(b"<FITID>xyz-100</FITID>", b"")
        primeira = ler_ofx(conteudo)[0].fitid
        segunda = ler_ofx(conteudo)[0].fitid
        # Precisa ser o mesmo entre leituras, senão a deduplicação não funciona.
        assert primeira == segunda
        assert "2026-08-10" in primeira

    def test_transacoes_saem_ordenadas_por_data(self):
        datas = [t.data for t in ler_ofx(OFX_1X)]
        assert datas == sorted(datas)

    def test_normaliza_espacos_da_descricao(self):
        conteudo = OFX_2X.replace(b"INTERNET FIBRA", b"INTERNET    FIBRA")
        assert ler_ofx(conteudo)[0].descricao == "INTERNET FIBRA"
