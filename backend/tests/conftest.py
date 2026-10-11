"""Fixtures compartilhadas pelos testes de API.

Todas as rotas de dados exigem sessão, então o `cliente` já vem autenticado.
Os testes que verificam a proteção em si usam `cliente_sem_login`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Espaco, MembroEspaco, PapelMembro, Usuario
from app.security import gerar_hash

EMAIL = "teste@exemplo.com"
SENHA = "senha-de-teste-123"


@pytest.fixture()
def sessao_teste(tmp_path):
    """Banco SQLite descartável, um por teste."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'teste.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def cliente_sem_login(sessao_teste):
    def _get_db():
        db = sessao_teste()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def criar_usuario_com_espaco(db, email: str, senha: str, nome_espaco: str) -> Usuario:
    """Um usuário e o espaço dele — desde o ADR-15, um não serve sem o outro.

    Sem espaço, toda consulta de dado financeiro volta vazia (o filtro da
    sessão usa um sentinela que não casa com nada), então um usuário sem
    espaço não consegue fazer nada além de ler o próprio perfil.
    """
    espaco = Espaco(nome=nome_espaco)
    db.add(espaco)
    db.flush()

    registro = Usuario(email=email, senha_hash=gerar_hash(senha), espaco_atual_id=espaco.id)
    db.add(registro)
    db.flush()

    db.add(MembroEspaco(espaco_id=espaco.id, usuario_id=registro.id, papel=PapelMembro.DONO))
    db.commit()
    return registro


@pytest.fixture()
def usuario(sessao_teste):
    db = sessao_teste()
    try:
        criar_usuario_com_espaco(db, EMAIL, SENHA, "Espaco de teste")
        return {"email": EMAIL, "senha": SENHA}
    finally:
        db.close()


@pytest.fixture()
def cliente(cliente_sem_login, usuario):
    """Cliente já autenticado: o token vai em toda requisição."""
    resposta = cliente_sem_login.post("/auth/login", json=usuario)
    assert resposta.status_code == 200, resposta.text
    cliente_sem_login.headers["Authorization"] = f"Bearer {resposta.json()['token']}"
    return cliente_sem_login


@pytest.fixture()
def conta(cliente):
    """Conta principal. Todo lançamento precisa de uma."""
    return cliente.post("/contas", json={"nome": "Mercado Pago"}).json()


@pytest.fixture()
def conta2(cliente):
    """Segunda conta, para os testes de transferência."""
    return cliente.post("/contas", json={"nome": "Nubank", "ordem": 1}).json()
