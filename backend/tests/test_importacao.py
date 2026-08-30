"""Testes do fluxo de importação de extrato: prévia, confirmação e regras."""

from __future__ import annotations

from datetime import date

import pytest

# O fixture `cliente`, já autenticado, vem de conftest.py.

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
def ano(cliente):
    cliente.post("/anos", json={"ano": 2026})
    return 2026


@pytest.fixture()
def comida(cliente):
    return cliente.post("/categorias", json={"nome": "Comida"}).json()


def enviar(cliente, conteudo=EXTRATO, formato="ofx"):
    return cliente.post(
        "/anos/2026/importacao/previa",
        files={"arquivo": (f"extrato.{formato}", conteudo, "application/octet-stream")},
        data={"formato": formato},
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
    def test_grava_apenas_o_que_foi_enviado(self, cliente, ano, comida, conta):
        previa = enviar(cliente).json()
        selecionadas = [
            {
                "fitid": t["fitid"],
                            "conta_id": conta["id"],
                "data": t["data"],
                "valor": t["valor"],
                "tipo": t["tipo_sugerido"],
                "descricao": t["descricao"],
            }
            for t in previa["transacoes"]
            if t["tipo_sugerido"] == "saida"
        ]

        resposta = cliente.post(
            "/anos/2026/importacao/confirmar", json={"transacoes": selecionadas}
        )
        assert resposta.status_code == 201
        assert resposta.json()["importadas"] == 2

        lancamentos = cliente.get("/anos/2026/lancamentos").json()
        assert len(lancamentos) == 2
        assert all(l["fitid"] for l in lancamentos)

    def test_reimportar_o_mesmo_extrato_nao_duplica(self, cliente, ano, conta):
        def confirmar():
            previa = enviar(cliente).json()
            return cliente.post(
                "/anos/2026/importacao/confirmar",
                json={
                    "transacoes": [
                        {
                            "fitid": t["fitid"],
                            "conta_id": conta["id"],
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

    def test_previa_marca_o_que_ja_foi_importado(self, cliente, ano, conta):
        previa = enviar(cliente).json()
        cliente.post(
            "/anos/2026/importacao/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": previa["transacoes"][0]["fitid"],
                        "conta_id": conta["id"],
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

    def test_aprende_regra_ao_confirmar(self, cliente, ano, comida, conta):
        previa = enviar(cliente).json()
        ifood = next(t for t in previa["transacoes"] if "IFOOD" in t["descricao"])

        resultado = cliente.post(
            "/anos/2026/importacao/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": ifood["fitid"],
                        "conta_id": conta["id"],
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

    def test_data_de_outro_ano_e_recusada(self, cliente, ano, conta):
        resposta = cliente.post(
            "/anos/2026/importacao/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": "x-1",
                        "conta_id": conta["id"],
                        "data": "2025-08-05",
                        "valor": "10.00",
                        "tipo": "saida",
                    }
                ]
            },
        )
        assert resposta.status_code == 422

    def test_categoria_em_entrada_e_recusada(self, cliente, ano, comida, conta):
        resposta = cliente.post(
            "/anos/2026/importacao/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": "x-2",
                        "conta_id": conta["id"],
                        "data": "2026-08-05",
                        "valor": "10.00",
                        "tipo": "entrada",
                        "categoria_id": comida["id"],
                    }
                ]
            },
        )
        assert resposta.status_code == 422

    def test_importado_entra_nos_totais(self, cliente, ano, comida, conta):
        previa = enviar(cliente).json()
        cliente.post(
            "/anos/2026/importacao/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": t["fitid"],
                            "conta_id": conta["id"],
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

    def test_usuario_pode_trocar_o_tipo_sugerido(self, cliente, ano, conta):
        """Uma transferência para a poupança parece saída no extrato, mas é
        'guardado' — e o usuário corrige isso na revisão."""
        previa = enviar(cliente).json()
        primeira = previa["transacoes"][0]

        cliente.post(
            "/anos/2026/importacao/confirmar",
            json={
                "transacoes": [
                    {
                        "fitid": primeira["fitid"],
                        "conta_id": conta["id"],
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


# --------------------------------------------------------------------------- #
# CSV e XLSX (ADR-08)
#
# O fluxo é o mesmo dos testes acima — o que muda é só o leitor. Estes testes
# existem para garantir que continua sendo o mesmo fluxo: dedupe, alerta de
# possível repetição e aprendizado de regra valem para os três formatos.
# --------------------------------------------------------------------------- #
EXTRATO_CSV = (
    "data;valor;descricao\n"
    "2026-08-05;-113,85;CLAUDE AI SUBSCRIPTION\n"
    "2026-08-06;-47,00;IFOOD RESTAURANTE\n"
    "2026-08-07;2000,00;SALARIO\n"
).encode("utf-8")


def extrato_xlsx() -> bytes:
    import io

    import openpyxl

    livro = openpyxl.Workbook()
    livro.active.append(["data", "valor", "descricao"])
    livro.active.append([date(2026, 8, 5), -113.85, "CLAUDE AI SUBSCRIPTION"])
    livro.active.append([date(2026, 8, 6), -47.00, "IFOOD RESTAURANTE"])
    livro.active.append([date(2026, 8, 7), 2000.00, "SALARIO"])
    buffer = io.BytesIO()
    livro.save(buffer)
    return buffer.getvalue()


def confirmar_tudo(cliente, conta, conteudo, formato):
    previa = enviar(cliente, conteudo, formato).json()
    return cliente.post(
        "/anos/2026/importacao/confirmar",
        json={
            "transacoes": [
                {
                    "fitid": t["fitid"],
                    "conta_id": conta["id"],
                    "data": t["data"],
                    "valor": t["valor"],
                    "tipo": t["tipo_sugerido"],
                    "descricao": t["descricao"],
                }
                for t in previa["transacoes"]
            ]
        },
    ).json()


class TestOutrosFormatos:
    @pytest.mark.parametrize("formato", ["csv", "xlsx"])
    def test_le_e_classifica_pelo_sinal(self, cliente, ano, formato):
        conteudo = EXTRATO_CSV if formato == "csv" else extrato_xlsx()
        dados = enviar(cliente, conteudo, formato).json()

        assert dados["total_lidas"] == 3
        assert [t["tipo_sugerido"] for t in dados["transacoes"]] == [
            "saida",
            "saida",
            "entrada",
        ]

    @pytest.mark.parametrize("formato", ["csv", "xlsx"])
    def test_reimportar_o_mesmo_extrato_nao_duplica(self, cliente, ano, conta, formato):
        conteudo = EXTRATO_CSV if formato == "csv" else extrato_xlsx()

        assert confirmar_tudo(cliente, conta, conteudo, formato)["importadas"] == 3
        segunda = confirmar_tudo(cliente, conta, conteudo, formato)
        assert segunda["importadas"] == 0
        assert segunda["ignoradas_duplicadas"] == 3
        assert len(cliente.get("/anos/2026/lancamentos").json()) == 3

    def test_o_mesmo_extrato_em_csv_e_xlsx_nao_duplica(self, cliente, ano, conta):
        """Baixar o extrato nos dois formatos é engano fácil de cometer."""
        assert confirmar_tudo(cliente, conta, EXTRATO_CSV, "csv")["importadas"] == 3
        segunda = confirmar_tudo(cliente, conta, extrato_xlsx(), "xlsx")
        assert segunda["importadas"] == 0
        assert len(cliente.get("/anos/2026/lancamentos").json()) == 3

    def test_mesma_data_e_valor_com_outra_descricao_e_so_possivel_repetido(
        self, cliente, ano, conta
    ):
        """Duas compras iguais no mesmo dia existem — não podem sumir sozinhas."""
        confirmar_tudo(cliente, conta, EXTRATO_CSV, "csv")

        parecido = b"data;valor;descricao\n2026-08-06;-47,00;OUTRO RESTAURANTE\n"
        linha = enviar(cliente, parecido, "csv").json()["transacoes"][0]

        assert linha["duplicado"] is False
        assert linha["possivel_repetido"] is True

    def test_regra_de_categoria_vale_para_csv(self, cliente, ano, comida):
        cliente.post("/regras", json={"padrao": "ifood", "categoria_id": comida["id"]})

        previa = enviar(cliente, EXTRATO_CSV, "csv").json()
        sugeridas = {
            t["descricao"]: t["categoria_sugerida_nome"] for t in previa["transacoes"]
        }
        assert sugeridas["IFOOD RESTAURANTE"] == "Comida"
        assert sugeridas["CLAUDE AI SUBSCRIPTION"] is None

    def test_planilha_sem_as_colunas_esperadas_da_erro_legivel(self, cliente, ano):
        resposta = enviar(cliente, b"quando;quanto;o que\n2026-08-05;-10;X\n", "csv")
        assert resposta.status_code == 422
        assert "colunas" in resposta.json()["detail"]

    def test_formato_errado_para_o_arquivo_da_erro_legivel(self, cliente, ano):
        """Escolher 'csv' no seletor e enviar o OFX é o engano mais provável."""
        resposta = enviar(cliente, EXTRATO, "csv")
        assert resposta.status_code == 422

    def test_formato_desconhecido_e_recusado(self, cliente, ano):
        resposta = cliente.post(
            "/anos/2026/importacao/previa",
            files={"arquivo": ("extrato.pdf", b"%PDF-1.4", "application/pdf")},
            data={"formato": "pdf"},
        )
        assert resposta.status_code == 422

    def test_formato_e_obrigatorio(self, cliente, ano):
        resposta = cliente.post(
            "/anos/2026/importacao/previa",
            files={"arquivo": ("extrato.csv", EXTRATO_CSV, "text/csv")},
        )
        assert resposta.status_code == 422
