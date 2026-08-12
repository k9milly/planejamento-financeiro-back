"""Testes do fluxo de importação de extrato: prévia, confirmação e regras."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

EXTRATO = b"""OFXHEADER:100
DATA:OFXSGML

<OFX><BANKTRANLIST>
<STMTTRN>
<DTPOSTED>20260805
<TRNAMT>-113.85
<FITID>nu-001
<MEMO>CLAUDE AI SUBSCRIPTION
</STMTTRN>
<STMTTRN>
<DTPOSTED>20260806
<TRNAMT>-47.00
<FITID>nu-002
<MEMO>IFOOD RESTAURANTE
</STMTTRN>
<STMTTRN>
<DTPOSTED>20260807
<TRNAMT>2000.00
<FITID>nu-003
<MEMO>SALARIO
</STMTTRN>
</BANKTRANLIST></OFX>
"""


@pytest.fixture()
def cliente(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'teste.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def ano(cliente):
    cliente.post("/anos", json={"ano": 2026})
    return 2026


@pytest.fixture()
def comida(cliente):
    return cliente.post("/categorias", json={"nome": "Comida"}).json()


def enviar(cliente, conteudo=EXTRATO):
    return cliente.post(
        "/anos/2026/importacao/ofx/previa",
        files={"arquivo": ("extrato.ofx", conteudo, "application/x-ofx")},
    )


class TestPrevia:
    def test_le_e_classifica_pelo_sinal(self, cliente, ano):
        dados = enviar(cliente).json()

        assert dados["total_lidas"] == 3
        assert dados["ja_importadas"] == 0

        tipos = [t["tipo_sugerido"] for t in dados["transacoes"]]
        assert tipos == ["saida", "saida", "entrada"]

    def test_nao_grava_nada(self, cliente, ano):
        enviar(cliente)
        assert cliente.get("/anos/2026/lancamentos").json() == []

    def test_arquivo_invalido_da_erro_legivel(self, cliente, ano):
        resposta = enviar(cliente, b"nao sou um extrato")
        assert resposta.status_code == 422
        assert "OFX" in resposta.json()["detail"]

    def test_arquivo_vazio_e_recusado(self, cliente, ano):
        assert enviar(cliente, b"").status_code == 422

    def test_marca_transacao_de_outro_ano(self, cliente, ano):
        conteudo = EXTRATO.replace(b"20260805", b"20250805")
        previa = enviar(cliente, conteudo).json()
        fora = [t for t in previa["transacoes"] if t["fora_do_ano"]]
        assert len(fora) == 1

    def test_ano_arquivado_recusa_importacao(self, cliente, ano):
        cliente.post("/anos/2026/arquivar")
        assert enviar(cliente).status_code == 409


class TestRegras:
    def test_regra_sugere_categoria(self, cliente, ano, comida):
        cliente.post("/regras", json={"padrao": "ifood", "categoria_id": comida["id"]})

        previa = enviar(cliente).json()
        ifood = next(t for t in previa["transacoes"] if "IFOOD" in t["descricao"])
        assert ifood["categoria_sugerida_nome"] == "Comida"

        # Sem regra, nada é sugerido — o app não chuta.
        claude = next(t for t in previa["transacoes"] if "CLAUDE" in t["descricao"])
        assert claude["categoria_sugerida_id"] is None

    def test_regra_ignora_acento_e_caixa(self, cliente, ano, comida):
        conteudo = EXTRATO.replace(b"IFOOD RESTAURANTE", b"Padaria Sao Joao")
        cliente.post(
            "/regras", json={"padrao": "são joão", "categoria_id": comida["id"]}
        )
        previa = enviar(cliente, conteudo).json()
        linha = next(t for t in previa["transacoes"] if "Padaria" in t["descricao"])
        assert linha["categoria_sugerida_nome"] == "Comida"

    def test_padrao_mais_especifico_vence(self, cliente, ano, comida):
        lazer = cliente.post("/categorias", json={"nome": "Lazer"}).json()
        conteudo = EXTRATO.replace(b"IFOOD RESTAURANTE", b"MERCADO LIVRE COMPRA")
        cliente.post("/regras", json={"padrao": "mercado", "categoria_id": comida["id"]})
        cliente.post(
            "/regras", json={"padrao": "mercado livre", "categoria_id": lazer["id"]}
        )

        previa = enviar(cliente, conteudo).json()
        linha = next(t for t in previa["transacoes"] if "MERCADO" in t["descricao"])
        assert linha["categoria_sugerida_nome"] == "Lazer"

    def test_padrao_repetido_atualiza_a_categoria(self, cliente, ano, comida):
        lazer = cliente.post("/categorias", json={"nome": "Lazer"}).json()
        cliente.post("/regras", json={"padrao": "ifood", "categoria_id": comida["id"]})
        cliente.post("/regras", json={"padrao": "IFOOD", "categoria_id": lazer["id"]})

        regras = cliente.get("/regras").json()
        assert len(regras) == 1
        assert regras[0]["categoria"]["nome"] == "Lazer"

    def test_previa_nao_altera_as_regras(self, cliente, ano, comida):
        """A normalização dos padrões acontece em memória; gravá-la de volta
        corromperia a regra que o usuário digitou."""
        cliente.post("/regras", json={"padrao": "ifood", "categoria_id": comida["id"]})
        antes = cliente.get("/regras").json()
        enviar(cliente)
        assert cliente.get("/regras").json() == antes


class TestConfirmacao:
    def test_grava_apenas_o_que_foi_enviado(self, cliente, ano, comida):
        previa = enviar(cliente).json()
        selecionadas = [
            {
                "fitid": t["fitid"],
                "data": t["data"],
                "valor": t["valor"],
                "tipo": t["tipo_sugerido"],
                "descricao": t["descricao"],
            }
            for t in previa["transacoes"]
            if t["tipo_sugerido"] == "saida"
        ]

        resposta = cliente.post(
            "/anos/2026/importacao/ofx/confirmar", json={"transacoes": selecionadas}
        )
        assert resposta.status_code == 201
        assert resposta.json()["importadas"] == 2

        lancamentos = cliente.get("/anos/2026/lancamentos").json()
        assert len(lancamentos) == 2
        assert all(l["fitid"] for l in lancamentos)

    def test_reimportar_o_mesmo_extrato_nao_duplica(self, cliente, ano):
        def confirmar():
            previa = enviar(cliente).json()
            return cliente.post(
                "/anos/2026/importacao/ofx/confirmar",
                json={
                    "transacoes": [
                        {
                            "fitid": t["fitid"],
                            "data": t["data"],
                            "valor": t["valor"],
                            "tipo": t["tipo_sugerido"],
                            "descricao": t["descricao"],
                        }
                        for t in previa["transacoes"]
                    ]
                },
            ).json()

        assert confirmar()["importadas"] == 3
        segunda = confirmar()
        assert segunda["importadas"] == 0
        assert segunda["ignoradas_duplicadas"] == 3
        assert len(cliente.get("/anos/2026/lancamentos").json()) == 3

    def test_previa_marca_o_que_ja_foi_importado(self, cliente, ano):
        previa = enviar(cliente).json()
        cliente.post(
            "/anos/2026/importacao/ofx/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": previa["transacoes"][0]["fitid"],
                        "data": previa["transacoes"][0]["data"],
                        "valor": previa["transacoes"][0]["valor"],
                        "tipo": "saida",
                    }
                ]
            },
        )

        segunda = enviar(cliente).json()
        assert segunda["ja_importadas"] == 1
        assert sum(t["duplicado"] for t in segunda["transacoes"]) == 1

    def test_aprende_regra_ao_confirmar(self, cliente, ano, comida):
        previa = enviar(cliente).json()
        ifood = next(t for t in previa["transacoes"] if "IFOOD" in t["descricao"])

        resultado = cliente.post(
            "/anos/2026/importacao/ofx/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": ifood["fitid"],
                        "data": ifood["data"],
                        "valor": ifood["valor"],
                        "tipo": "saida",
                        "categoria_id": comida["id"],
                        "descricao": ifood["descricao"],
                        "aprender_padrao": "ifood",
                    }
                ]
            },
        ).json()

        assert resultado["regras_criadas"] == 1
        assert cliente.get("/regras").json()[0]["padrao"] == "IFOOD"

    def test_data_de_outro_ano_e_recusada(self, cliente, ano):
        resposta = cliente.post(
            "/anos/2026/importacao/ofx/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": "x-1",
                        "data": "2025-08-05",
                        "valor": "10.00",
                        "tipo": "saida",
                    }
                ]
            },
        )
        assert resposta.status_code == 422

    def test_categoria_em_entrada_e_recusada(self, cliente, ano, comida):
        resposta = cliente.post(
            "/anos/2026/importacao/ofx/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": "x-2",
                        "data": "2026-08-05",
                        "valor": "10.00",
                        "tipo": "entrada",
                        "categoria_id": comida["id"],
                    }
                ]
            },
        )
        assert resposta.status_code == 422

    def test_importado_entra_nos_totais(self, cliente, ano, comida):
        previa = enviar(cliente).json()
        cliente.post(
            "/anos/2026/importacao/ofx/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": t["fitid"],
                        "data": t["data"],
                        "valor": t["valor"],
                        "tipo": t["tipo_sugerido"],
                        "categoria_id": (
                            comida["id"] if t["tipo_sugerido"] == "saida" else None
                        ),
                        "descricao": t["descricao"],
                    }
                    for t in previa["transacoes"]
                ]
            },
        )

        agosto = cliente.get("/anos/2026/resumo").json()["meses"][7]
        assert agosto["entradas"] == "2000.00"
        assert agosto["saidas"] == "160.85"
        assert agosto["gastos_por_categoria"][0]["categoria"] == "Comida"

    def test_usuario_pode_trocar_o_tipo_sugerido(self, cliente, ano):
        """Uma transferência para a poupança parece saída no extrato, mas é
        'guardado' — e o usuário corrige isso na revisão."""
        previa = enviar(cliente).json()
        primeira = previa["transacoes"][0]

        cliente.post(
            "/anos/2026/importacao/ofx/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": primeira["fitid"],
                        "data": primeira["data"],
                        "valor": primeira["valor"],
                        "tipo": "guardado",
                    }
                ]
            },
        )

        agosto = cliente.get("/anos/2026/resumo").json()["meses"][7]
        assert agosto["saidas"] == "0.00"
        assert agosto["guardado_no_mes"] == "113.85"
