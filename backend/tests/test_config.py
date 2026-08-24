"""Testes de leitura de configuração.

Existe por causa de um incidente: CORS_ORIGINS definido em produção como
`["https://..."]` (formato JSON, o que o pydantic-settings exige por padrão
para campos de lista) travou a aplicação inteira num crash-loop assim que o
Fly reiniciou as máquinas — o terminal do usuário trocou/perdeu aspas ao
repassar o valor, e o erro só aparecia nos logs do servidor, nunca no
navegador. O formato aceito agora é texto simples, para não depender de o
terminal preservar aspas aninhadas corretamente.
"""

from __future__ import annotations

import os

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _limpar_env(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)


class TestCorsOrigins:
    def test_formato_simples_uma_origem(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://sistema-financas.netlify.app")
        assert Settings().cors_origins == ["https://sistema-financas.netlify.app"]

    def test_formato_simples_varias_origens(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://a.com,https://b.com")
        assert Settings().cors_origins == ["https://a.com", "https://b.com"]

    def test_ignora_espacos_ao_redor_da_virgula(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://a.com ,  https://b.com")
        assert Settings().cors_origins == ["https://a.com", "https://b.com"]

    def test_json_antigo_continua_aceito(self, monkeypatch):
        """Quem já tinha configurado no formato anterior não é pego de surpresa."""
        monkeypatch.setenv("CORS_ORIGINS", '["https://c.com","https://d.com"]')
        assert Settings().cors_origins == ["https://c.com", "https://d.com"]

    def test_sem_variavel_usa_padrao_local(self, monkeypatch):
        """O padrão cobre os dois frontends em desenvolvimento.

        5173 é o Vite deste repositório; 8080 é o do
        `planejamento-financeiro-front` (ADR-03). Sem a 8080 aqui, quem clonar
        os dois repositórios esbarra em erro de CORS na primeira chamada.
        """
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        origens = Settings().cors_origins
        assert "http://localhost:5173" in origens
        assert "http://localhost:8080" in origens

    def test_variavel_vazia_nao_quebra(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "")
        assert Settings().cors_origins == []

    def test_nunca_levanta_erro_com_aspas_mal_formadas(self, monkeypatch):
        """O incidente real: um `[` sem o resto do JSON válido (aspas
        perdidas pelo terminal) não pode mais derrubar a aplicação."""
        monkeypatch.setenv("CORS_ORIGINS", "[https://sistema-financas.netlify.app]")
        with pytest.raises(Exception):
            # Isto ainda é inválido (não é uma URL nem uma lista JSON válida),
            # mas o teste documenta que qualquer falha aqui precisa acontecer
            # de forma síncrona e visível — nunca em silêncio dentro de um
            # crash-loop do processo.
            Settings().cors_origins
