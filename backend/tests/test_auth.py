"""Testes de autenticação e proteção das rotas."""

from __future__ import annotations

import pytest

from app.security import conferir_senha, criar_token, gerar_hash, ler_token


class TestHashDeSenha:
    def test_senha_nunca_e_guardada_em_texto(self):
        hash_gerado = gerar_hash("minha-senha-secreta")
        assert "minha-senha-secreta" not in hash_gerado
        assert hash_gerado.startswith("$2b$")

    def test_mesma_senha_gera_hashes_diferentes(self):
        """O bcrypt embute um sal aleatório: dois hashes iguais denunciariam
        que duas pessoas usam a mesma senha."""
        assert gerar_hash("igual") != gerar_hash("igual")

    def test_confere_a_senha_certa(self):
        assert conferir_senha("certa", gerar_hash("certa"))

    def test_recusa_a_senha_errada(self):
        assert not conferir_senha("errada", gerar_hash("certa"))

    def test_hash_malformado_nao_quebra(self):
        assert not conferir_senha("qualquer", "isto-nao-e-um-hash")

    def test_senha_muito_longa_e_aceita(self):
        """O bcrypt trunca em 72 bytes e versões recentes levantam erro em vez
        de cortar sozinhas."""
        longa = "a" * 200
        assert conferir_senha(longa, gerar_hash(longa))


class TestToken:
    def test_token_carrega_o_usuario(self):
        assert ler_token(criar_token(42)) == 42

    def test_token_adulterado_e_recusado(self):
        token = criar_token(1)
        assert ler_token(token[:-4] + "xxxx") is None

    def test_lixo_e_recusado(self):
        assert ler_token("nao-e-um-token") is None
        assert ler_token("") is None


class TestLogin:
    def test_login_devolve_token(self, cliente_sem_login, usuario):
        resposta = cliente_sem_login.post("/auth/login", json=usuario)
        assert resposta.status_code == 200
        assert resposta.json()["token"]
        assert resposta.json()["email"] == usuario["email"]

    def test_senha_errada_e_recusada(self, cliente_sem_login, usuario):
        resposta = cliente_sem_login.post(
            "/auth/login", json={"email": usuario["email"], "senha": "errada"}
        )
        assert resposta.status_code == 401

    def test_email_inexistente_da_a_mesma_mensagem(self, cliente_sem_login, usuario):
        """Mensagens diferentes revelariam quais e-mails estão cadastrados."""
        inexistente = cliente_sem_login.post(
            "/auth/login", json={"email": "ninguem@exemplo.com", "senha": "x12345678"}
        )
        errada = cliente_sem_login.post(
            "/auth/login", json={"email": usuario["email"], "senha": "errada"}
        )
        assert inexistente.status_code == errada.status_code == 401
        assert inexistente.json()["detail"] == errada.json()["detail"]

    def test_nao_existe_cadastro_aberto(self, cliente_sem_login):
        resposta = cliente_sem_login.post(
            "/auth/registrar", json={"email": "novo@exemplo.com", "senha": "12345678"}
        )
        assert resposta.status_code == 404

    def test_eu_identifica_a_sessao(self, cliente, usuario):
        assert cliente.get("/auth/eu").json()["email"] == usuario["email"]


class TestProtecao:
    # Uma rota de cada router: se alguma nascer desprotegida, o teste acusa.
    ROTAS = [
        ("get", "/anos"),
        ("post", "/anos"),
        ("get", "/categorias"),
        ("post", "/categorias"),
        ("get", "/anos/2026/resumo"),
        ("get", "/anos/2026/lancamentos"),
        ("post", "/anos/2026/lancamentos"),
        ("delete", "/anos/2026/lancamentos/1"),
        ("get", "/anos/2026/gastos-fixos"),
        ("get", "/anos/2026/wishlist"),
        ("get", "/anos/2026/wishlist/total"),
        ("get", "/regras"),
        ("post", "/anos/2026/importacao/ofx/confirmar"),
    ]

    @pytest.mark.parametrize("metodo,rota", ROTAS)
    def test_rota_exige_sessao(self, cliente_sem_login, metodo, rota):
        resposta = getattr(cliente_sem_login, metodo)(rota)
        assert resposta.status_code == 401, f"{metodo.upper()} {rota} ficou aberta"

    def test_token_invalido_e_recusado(self, cliente_sem_login):
        cliente_sem_login.headers["Authorization"] = "Bearer nao-vale"
        assert cliente_sem_login.get("/anos").status_code == 401

    def test_saude_continua_publica(self, cliente_sem_login):
        """O healthcheck precisa responder sem token para o serviço de
        hospedagem saber se a aplicação está de pé."""
        assert cliente_sem_login.get("/saude").status_code == 200

    def test_usuario_desativado_perde_o_acesso(self, cliente, sessao_teste, usuario):
        assert cliente.get("/anos").status_code == 200

        db = sessao_teste()
        try:
            from app.models import Usuario

            registro = db.query(Usuario).filter(Usuario.email == usuario["email"]).one()
            registro.ativo = False
            db.commit()
        finally:
            db.close()

        # O token continua tecnicamente válido, mas não deve mais servir.
        assert cliente.get("/anos").status_code == 401
