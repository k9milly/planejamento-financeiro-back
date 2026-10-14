"""A conexão sobrevive a ficar parada (pool_pre_ping).

O Postgres de produção é serverless (Neon) e encerra a conexão quando o banco
fica ocioso; a máquina no Fly também dorme. O pool do SQLAlchemy não sabe disso
e guarda o socket morto, então a **primeira** requisição depois de um tempo
parado estourava com `OperationalError` e um `500`, e a seguinte funcionava.

Visto no log de produção em 13/10/2026: `GET /contas` deu `500` na primeira
chamada depois de a máquina religar, e `200` em todas as outras.

Estes testes derrubam a conexão por baixo do pool de propósito — é o que o
banco ocioso faz do outro lado — e conferem que a aplicação se recupera sozinha.
Não dá para reproduzir isso contra o Neon numa suíte, mas o mecanismo do pool é
o mesmo em qualquer dialeto, então o SQLite serve de laboratório.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.database import criar_engine, engine


def _matar_conexao_do_pool(motor) -> None:
    """Devolve uma conexão ao pool e a fecha por baixo.

    É o que acontece quando o banco do outro lado encerra a sessão: o pool
    continua achando que tem uma conexão boa guardada.
    """
    conexao = motor.connect()
    bruta = conexao.connection.dbapi_connection
    conexao.close()  # volta para o pool, viva aos olhos dele
    bruta.close()  # e morre sem o pool saber


def test_conexao_morta_no_pool_e_substituida(tmp_path):
    """Com pre-ping, a requisição seguinte funciona como se nada tivesse havido."""
    motor = criar_engine(f"sqlite:///{tmp_path / 'pre_ping.db'}")
    with motor.connect() as c:
        c.execute(sa.text("create table t (x integer)"))
        c.commit()

    _matar_conexao_do_pool(motor)

    with motor.connect() as c:
        assert c.execute(sa.text("select count(*) from t")).scalar() == 0


def test_a_regressao_seria_detectada(tmp_path):
    """Sem pre-ping, a mesma sequência estoura.

    O contrapeso: sem ele, `test_conexao_morta_no_pool_e_substituida` poderia
    passar porque o pool descartou a conexão por outro motivo, e a proteção
    viraria enfeite. Se este teste parar de falhar, é o laboratório que deixou
    de reproduzir o problema — e aí o outro não prova mais nada.
    """
    motor = sa.create_engine(
        f"sqlite:///{tmp_path / 'sem_pre_ping.db'}",
        connect_args={"check_same_thread": False},
    )
    with motor.connect() as c:
        c.execute(sa.text("create table t (x integer)"))
        c.commit()

    _matar_conexao_do_pool(motor)

    with pytest.raises(Exception) as erro:
        with motor.connect() as c:
            c.execute(sa.text("select count(*) from t"))
    assert "closed" in str(erro.value).lower()


def test_a_engine_da_aplicacao_tem_pre_ping():
    """A engine que a aplicação usa de verdade, não só a do teste.

    Os dois testes acima exercitam `criar_engine`; este amarra o módulo a ela,
    para ninguém voltar a montar a engine da aplicação por fora e perder a
    configuração sem nenhum teste reclamar.
    """
    assert engine.pool._pre_ping is True
