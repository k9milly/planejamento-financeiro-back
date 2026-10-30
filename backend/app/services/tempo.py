"""Que dia é hoje, do ponto de vista de quem usa o app.

O servidor roda em UTC (Fly.io) e o banco grava `criada_em` em UTC. Quem usa o
app está no Brasil, e `Lancamento.data` é a data do calendário que a pessoa
escolheu na tela — já no fuso dela. Misturar as duas coisas cria um bug que só
aparece **entre 21h e meia-noite**, quando lá já é o dia seguinte:

    22h05 de 05/09 no Brasil  ->  já é 06/09 em UTC

Foi exatamente assim que uma meta com prazo criada às 22h passou a ignorar
tudo o que tinha sido guardado naquele mesmo dia: o `criada_em` dela dizia
06/09, os lançamentos diziam 05/09, e a comparação `data >= criada_em`
excluía o dia inteiro. No dia seguinte o progresso "voltava" sozinho, o que
torna o problema difícil de acreditar quando alguém relata.

Por isso todo lugar que pergunta "que dia é hoje" ou "que dia foi isto"
passa por aqui, e nenhum usa `date.today()` direto.

Fuso fixo, não configurável: é um app de finanças pessoais de uma pessoa só,
no Brasil. O Brasil não usa mais horário de verão desde 2019, mas `ZoneInfo`
cuidaria disso de qualquer forma — melhor do que subtrair três horas na mão.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    """A data de hoje no fuso de quem usa, não no do servidor."""
    return datetime.now(FUSO).date()


def agora() -> datetime:
    """O instante atual, em UTC e sem fuso — igual ao que o banco grava.

    Todo carimbo de tempo deste projeto nasce de `server_default=func.now()`,
    que grava UTC sem fuso tanto no Postgres quanto no SQLite. Um campo
    preenchido pelo Python com `datetime.now()` sai no fuso **do servidor**:
    em produção (Fly, UTC) coincide por acaso, e na máquina de quem
    desenvolve, não — o mesmo campo passa a significar duas coisas conforme
    onde o processo roda, e `data_local()`, que assume UTC, erra em três
    horas.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def data_local(momento: datetime) -> date:
    """A data de um `criada_em` do banco, no fuso de quem usa.

    Timestamps sem fuso vindos do banco são UTC — é o que `func.now()` grava
    tanto no Postgres quanto no SQLite. Um timestamp que já venha com fuso é
    apenas convertido.
    """
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO).date()
