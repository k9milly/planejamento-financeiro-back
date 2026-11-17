"""O script que exporta o `openapi.json` para o teste de contrato (ADR-20).

O arquivo exportado é o que o frontend usa para conferir cada URL que o
`api-client` monta. Se ele sair vazio, truncado ou sem os caminhos, o teste
de lá passa a não provar nada — e passa **em silêncio**, que é o modo de
falha que o ADR-20 existe para fechar.
"""

from __future__ import annotations

import json

from scripts.exportar_openapi import principal


def test_escreve_um_json_valido_com_os_caminhos(tmp_path):
    destino = tmp_path / "openapi.json"
    assert principal([str(destino)]) == 0

    esquema = json.loads(destino.read_text(encoding="utf-8"))
    assert esquema["paths"], "esquema sem caminho nenhum"
    assert "/auth/login" in esquema["paths"]


def test_cria_a_pasta_de_destino(tmp_path):
    destino = tmp_path / "contrato" / "openapi.json"
    assert principal([str(destino)]) == 0
    assert destino.exists()


def test_a_rota_da_fatura_leva_o_mes_no_caminho(tmp_path):
    """O bug que motivou o ADR-20, virado em teste.

    O frontend chamou `/fatura?mes=11` por quase três meses, e a rota sempre
    foi `/fatura/{mes}`. Este teste trava a forma publicada: se `/fatura` sem
    o mês aparecesse no esquema, a URL errada passaria a ser válida e o teste
    de contrato do front deixaria de pegá-la.
    """
    destino = tmp_path / "openapi.json"
    principal([str(destino)])
    caminhos = json.loads(destino.read_text(encoding="utf-8"))["paths"]

    assert "/anos/{ano}/cartoes/{cartao_id}/fatura/{mes}" in caminhos
    assert "/anos/{ano}/cartoes/{cartao_id}/fatura" not in caminhos


def test_indentado_por_padrao(tmp_path):
    """O arquivo é versionado no front; em linha única o diff seria ilegível."""
    destino = tmp_path / "openapi.json"
    principal([str(destino)])
    assert "\n  " in destino.read_text(encoding="utf-8")
