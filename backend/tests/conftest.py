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
from app.models import Usuario
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


@pytest.fixture()
def usuario(sessao_teste):
    db = sessao_teste()
    try:
        registro = Usuario(email=EMAIL, senha_hash=gerar_hash(SENHA))
        db.add(registro)
        db.commit()
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
