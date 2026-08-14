"""Testes do script de cópia para o Postgres.

Existe porque o script mexe em dados reais numa operação de mão única: se ele
esquecer uma tabela, a descoberta acontece com o banco de produção já no ar.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Ano, Conta, Lancamento, TipoLancamento, Usuario
from app.security import gerar_hash
from scripts.copiar_para_postgres import ORDEM, copiar


def test_ordem_cobre_todas_as_tabelas():
    """Toda tabela mapeada precisa estar na lista de cópia.

    Foi assim que `contas` ficou de fora quando o modelo de contas nasceu: o
    script continuou "funcionando", só que sem copiar as contas.
    """
    mapeadas = set(Base.metadata.tables) - {"alembic_version"}
    na_copia = {modelo.__tablename__ for modelo in ORDEM}
    assert mapeadas == na_copia, (
        f"faltando na cópia: {mapeadas - na_copia}; "
        f"sobrando: {na_copia - mapeadas}"
    )


def test_ordem_respeita_as_dependencias():
    """Uma tabela só pode ser copiada depois daquelas de que depende."""
    posicao = {modelo.__tablename__: i for i, modelo in enumerate(ORDEM)}

    for modelo in ORDEM:
        for coluna in modelo.__table__.columns:
            for fk in coluna.foreign_keys:
                alvo = fk.column.table.name
                if alvo == modelo.__tablename__:
                    continue  # autorreferência não impõe ordem entre tabelas
                assert posicao[alvo] < posicao[modelo.__tablename__], (
                    f"{modelo.__tablename__} depende de {alvo}, "
                    "que precisa vir antes na ordem de cópia"
                )


def _preparar(caminho, com_dados: bool):
    engine = create_engine(f"sqlite:///{caminho}")
    Base.metadata.create_all(bind=engine)
    Sessao = sessionmaker(bind=engine)

    if com_dados:
        with Sessao() as s:
            conta = Conta(id=1, nome="Mercado Pago", cor="#00b1ea", ordem=0)
            s.add(conta)
            s.add(Usuario(id=1, email="a@b.com", senha_hash=gerar_hash("x12345678")))
            s.add(Ano(id=1, ano=2026))
            s.flush()
            s.add(
                Lancamento(
                    ano_id=1,
                    conta_id=1,
                    mes=4,
                    data=date(2026, 4, 6),
                    valor=100,
                    tipo=TipoLancamento.ENTRADA,
                    descricao="salário",
                )
            )
            s.commit()

    return f"sqlite:///{caminho}", Sessao


def test_copia_leva_tudo(tmp_path):
    origem_url, _ = _preparar(tmp_path / "origem.db", com_dados=True)
    destino_url, SessaoDestino = _preparar(tmp_path / "destino.db", com_dados=False)

    copiar(origem_url, destino_url, simular=False)

    with SessaoDestino() as s:
        assert s.scalar(select(func.count()).select_from(Lancamento)) == 1
        assert s.scalar(select(func.count()).select_from(Conta)) == 1
        # Os ids são preservados: as chaves estrangeiras dependem disso.
        assert s.get(Lancamento, 1).conta_id == 1


def test_simulacao_nao_grava(tmp_path):
    origem_url, _ = _preparar(tmp_path / "origem.db", com_dados=True)
    destino_url, SessaoDestino = _preparar(tmp_path / "destino.db", com_dados=False)

    copiar(origem_url, destino_url, simular=True)

    with SessaoDestino() as s:
        assert s.scalar(select(func.count()).select_from(Lancamento)) == 0


def test_recusa_copiar_para_a_propria_origem(tmp_path):
    """O erro que aconteceu de verdade: DATABASE_URL apontando para o destino
    fazia o script ler dele mesmo e copiar zero registros."""
    origem_url, _ = _preparar(tmp_path / "origem.db", com_dados=True)

    with pytest.raises(SystemExit):
        copiar(origem_url, origem_url, simular=True)
