"""Isolamento de dados por espaço financeiro (ADR-15).

Este arquivo é curto e carrega a parte mais arriscada do sistema. Se algo aqui
estiver errado, o dinheiro de uma família aparece para outra — então vale ler
inteiro antes de mexer.

## O problema

Até o ADR-15, login decidia **quem entra**, não **o que a pessoa vê**: as
catorze tabelas de dinheiro eram globais. A correção óbvia seria escrever
`.filter(espaco_id == o meu)` em toda consulta de todo router. Essa correção
funciona no dia em que é escrita e falha no primeiro router novo em que alguém
esquecer — e o esquecimento é silencioso: a tela mostra dados a mais e nada
acusa erro.

## A solução: filtrar na sessão, não no router

O SQLAlchemy deixa interceptar **toda** consulta que passa pela sessão. Em vez
de catorze tabelas × dezenas de consultas que precisam lembrar da regra, há um
lugar só que a aplica. Um router novo nasce protegido sem fazer nada, e um
router que tente escapar precisa sair da sessão de propósito (SQL cru), o que é
visível em revisão.

## Por que o espaço mora na sessão, e não num `ContextVar`

O ADR-15 propunha guardar o espaço ativo num `contextvars.ContextVar`. **Isso
não funciona com o FastAPI**, e a razão é sutil o bastante para merecer estar
escrita aqui.

O FastAPI roda dependências e endpoints **síncronos** num pool de threads, cada
chamada com uma *cópia* do contexto. Um `ContextVar.set()` feito dentro da
dependência de autenticação acontece na cópia dela e morre ali — quando o
endpoint roda, em outra chamada, vê o valor antigo:

    await anyio.to_thread.run_sync(dependencia)   # faz var.set(42)
    await anyio.to_thread.run_sync(endpoint)      # var.get() -> None

A `Session` do banco não tem esse problema: é **um objeto só**, criado por
requisição em `get_db` e entregue à dependência e ao endpoint. Pendurar o
espaço nela (`session.info`) faz o dado viajar junto de quem vai usá-lo, sem
depender de como o framework agenda threads. De quebra, fica impossível uma
requisição ler a sessão de outra — o isolamento vem da estrutura, não de
disciplina.

## Quando não há espaço na sessão, nada é filtrado — e por que isso é seguro

Fora de uma requisição autenticada (scripts, migrações, testes de unidade) a
sessão não tem espaço e nenhum filtro é aplicado. Parece um buraco, mas não é:
quem preenche é `deps.usuario_atual`, a dependência que já exige token válido
em toda rota de dado. Sem passar por ela, não há requisição autenticada
acontecendo.

O risco real é o inverso — usuário autenticado **sem** espaço escolhido. Esse
caso não pode cair no "sem filtro", senão ver tudo seria o padrão de quem não
escolheu nada. Por isso existe `SEM_ESPACO`: um id que nenhuma linha tem, então
as consultas voltam vazias. Falha fechado.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.database import Base
from app.models import ComEspaco

# Onde o espaço ativo fica pendurado dentro da sessão.
CHAVE = "espaco_id"

# Para usuário autenticado que ainda não escolheu espaço. Nenhuma linha tem
# este id, então toda consulta volta vazia. Deixar a sessão sem espaço faria o
# oposto: desligaria o filtro e mostraria tudo.
SEM_ESPACO = -1


def fixar_espaco(db: Session, espaco_id: int | None) -> None:
    """Diz a esta sessão qual espaço ela enxerga. Chamado por `usuario_atual`."""
    db.info[CHAVE] = espaco_id


def espaco_da_sessao(db: Session) -> int | None:
    return db.info.get(CHAVE)


def modelos_protegidos() -> list[type]:
    """As tabelas que guardam dinheiro, descobertas por herança.

    Deliberadamente **não** é uma lista escrita à mão. Uma lista é algo que
    alguém precisa lembrar de atualizar ao criar a décima quinta tabela, e
    esquecer significaria uma tabela sem isolamento — o tipo exato de falha
    silenciosa que este módulo existe para evitar. Herdando de `ComEspaco`, a
    tabela nova ou entra na proteção ou nem tem a coluna.
    """
    return [
        mapeador.class_
        for mapeador in Base.registry.mappers
        if issubclass(mapeador.class_, ComEspaco)
    ]


@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_espaco(estado) -> None:
    """Toda leitura só enxerga o espaço da sessão.

    `with_loader_criteria` e não um `where` cru: ele alcança também o que vem
    carregado por relacionamento na mesma consulta — o
    `joinedload(Lancamento.categoria)` que os routers usam, por exemplo. Um
    filtro aplicado só à entidade principal deixaria esses passarem.

    `include_aliases=True` cobre a mesma tabela aparecendo duas vezes na
    consulta, que é o caso de `Lancamento.conta` e `conta_destino`.
    """
    if not estado.is_select or estado.is_column_load or estado.is_relationship_load:
        return

    espaco_id = estado.session.info.get(CHAVE)
    if espaco_id is None:
        return

    for modelo in modelos_protegidos():
        estado.statement = estado.statement.options(
            with_loader_criteria(
                modelo,
                lambda cls: cls.espaco_id == espaco_id,
                include_aliases=True,
            )
        )


@event.listens_for(Session, "before_flush")
def _carimbar_espaco_em_novos(sessao: Session, _contexto, _instancias) -> None:
    """Linha nova herda o espaço da sessão, se ainda não tiver um.

    Evita que cada `criar()` de cada router precise lembrar de preencher o
    campo — a mesma disciplina que o filtro de leitura existe para não exigir.
    Não sobrescreve quem já definiu: o cadastro (ADR-16) cria o primeiro espaço
    de alguém e precisa dizer explicitamente qual é.
    """
    espaco_id = sessao.info.get(CHAVE)
    if espaco_id is None or espaco_id == SEM_ESPACO:
        return

    for objeto in sessao.new:
        if isinstance(objeto, ComEspaco) and objeto.espaco_id is None:
            objeto.espaco_id = espaco_id


def apagar_espaco(db: Session, espaco_id: int) -> None:
    """Apaga um espaço e tudo que havia dentro dele, na ordem certa.

    ## Por que não basta apagar a linha de `espacos`

    `espaco_id` é `CASCADE` em toda tabela, então `DELETE FROM espacos` parece
    suficiente — e **não é**. O banco, ao apagar o espaço, apaga `contas`
    também; e `lancamentos.conta_id` é `RESTRICT`, de propósito, porque apagar
    uma conta que tem lançamentos é um engano que o sistema deve recusar. O
    mesmo vale para `gastos_fixos`, `caixinhas` e `compras_parceladas`.

    As duas regras estão certas separadas e se contradizem juntas. Quem resolve
    é este código, dizendo a ordem: filho antes de pai. O banco não tem como
    adivinhar que, neste caso, a conta vai embora porque o espaço inteiro vai.

    ## Por que a ordem vem do metadata

    `Base.metadata.sorted_tables` devolve as tabelas em ordem topológica de
    chave estrangeira — pai antes de filho. Apagar é o caminho inverso, então
    o laço percorre a lista ao contrário. Assim a ordem sai da estrutura
    declarada, e não de uma lista escrita à mão que alguém precisaria reordenar
    ao criar a próxima tabela.

    ## Como este defeito passou pelos testes

    Ele não dependia de dialeto, e sim de **ordem de criação das tabelas**: o
    SQLite dispara os cascatas na ordem em que as chaves estrangeiras foram
    declaradas, e `create_all` (que os testes usam) produz uma ordem em que
    isto funciona, enquanto a migração produz outra em que `contas` é apagada
    antes de `lancamentos`. A suíte passava por sorte. Depois desta função a
    ordem deixa de ser do banco e passa a ser nossa, nos dois dialetos — e há
    teste rodando contra um banco **migrado**, não só contra `create_all`.
    """
    protegidas = {modelo.__tablename__ for modelo in modelos_protegidos()}
    # `membros_espaco` entra junto: o vínculo não é dado financeiro, mas
    # pertence ao espaço e morre com ele.
    protegidas.add("membros_espaco")

    # `usuarios` fica de fora de propósito: quem participava do espaço
    # continua existindo, e `espaco_atual_id` é `SET NULL`.
    for tabela in reversed(Base.metadata.sorted_tables):
        if tabela.name in protegidas:
            db.execute(tabela.delete().where(tabela.c.espaco_id == espaco_id))

    db.execute(
        Base.metadata.tables["espacos"]
        .delete()
        .where(Base.metadata.tables["espacos"].c.id == espaco_id)
    )
