# ADR-15 — Espaços financeiros compartilhados e isolamento de dados

**Status:** proposto

## Contexto

Toda a revisão de segurança feita nesta rodada (ver mensagem anexa) apontou
o mesmo ponto como o mais importante: hoje o sistema não tem **nenhum**
isolamento de dados por usuário. `Ano`, `Conta`, `Categoria`, `Lancamento`,
`GastoFixo`, `MetaPoupanca`, `Caixinha`, `ItemWishlist`,
`RegraCategorizacao` — todas as tabelas de dinheiro são globais. Login
decide **quem entra**, não **o que essa pessoa vê**. Isso é seguro hoje
porque só existe uma conta real (a da Kamilly); deixa de ser seguro no
instante em que uma segunda conta existir.

A Kamilly confirmou que quer o sistema usável por várias pessoas, e — indo
além do que a revisão original cobria — quer **permitir que contas
compartilhem o mesmo conjunto de dados** (o caso dela mesma com um
parceiro, dividindo o controle financeiro do casal). Isso significa que
"isolar por usuário" não é a modelagem certa — a unidade de isolamento não
é a pessoa, é o **espaço financeiro**, que pode ter uma ou várias pessoas
dentro.

## Decisão

### `Espaco` é a unidade de isolamento, não `Usuario`

```python
class Espaco(Base):
    __tablename__ = "espacos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PapelMembro(str, enum.Enum):
    DONO = "dono"      # único que convida, remove membro, renomeia e apaga o espaço
    MEMBRO = "membro"   # mesmo acesso aos dados financeiros que o dono — só não administra


class MembroEspaco(Base):
    __tablename__ = "membros_espaco"
    __table_args__ = (UniqueConstraint("espaco_id", "usuario_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    espaco_id: Mapped[int] = mapped_column(ForeignKey("espacos.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    papel: Mapped[PapelMembro] = mapped_column(Enum(PapelMembro, native_enum=False))
    entrou_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

Um `Usuario` pode ser membro de vários espaços (a própria conta solo, mais
um espaço de casal, por exemplo). Dentro de cada espaço, **dono e membro têm
o mesmo acesso aos dados financeiros** — a diferença é só administrativa
(convidar, remover, apagar o espaço). Isso é de propósito: o caso real que
motivou isto é um casal dividindo o controle financeiro, e permissão
graduada ("membro só lê, não edita") resolveria um problema que a Kamilly
não pediu, à custa de complexidade real.

`Usuario` ganha `espaco_atual_id` (qual espaço está sendo visto agora —
igual um seletor de workspace):

```python
class Usuario(Base):
    ...
    espaco_atual_id: Mapped[int | None] = mapped_column(
        ForeignKey("espacos.id", ondelete="SET NULL"), nullable=True, index=True
    )
```

Guardado no banco, não no `localStorage` do navegador — mesma razão já
usada para outras preferências deste projeto (ADR-11): a pessoa pode abrir
de outro aparelho e deveria continuar vendo o mesmo espaço. Novo endpoint:

```ts
// PATCH /auth/espaco-atual
interface EspacoAtualAtualizar { espaco_id: number; }
// 422 se o usuário não for membro desse espaço.
```

### Toda tabela de dado financeiro ganha `espaco_id` — sem exceção, mesmo as já transitivamente ligadas a um `Ano`

Decisão deliberada: em vez de só as tabelas hoje "globais" (`Conta`,
`Categoria`, `MetaPoupanca`, `Caixinha`, `RegraCategorizacao`,
`CorFormaPagamento`, `CompraParcelada` do ADR-14) ganharem `espaco_id`
direto e as demais (`Lancamento`, `GastoFixo`, `GastoFixoMensal`,
`SaldoInicial`, `FaturaMensal`, `ItemWishlist`) ficarem isoladas só
*transitivamente* por pertencerem a um `Ano` já filtrado — **todas** as
catorze tabelas ganham `espaco_id` direto, incluindo `Ano` em si.

**Por quê, já que é redundante para quem já tem `ano_id`:** porque permite
um único mecanismo de proteção, aplicado por igual a toda tabela, em vez de
dois raciocínios diferentes ("esta tabela se protege sozinha, aquela se
protege porque confia no `Ano` que ela referencia"). Um raciocínio só é mais
fácil de auditar — e o risco de errar aqui (uma consulta que escapa do
filtro) é vazar os dados financeiros de uma família para outra, não um bug
cosmético. Vale a coluna extra em todas as tabelas pela simplicidade de ter
uma regra sem exceção.

### O isolamento é imposto pelo SQLAlchemy, não por disciplina de cada router

Em vez de confiar que toda consulta em todo router, hoje e no futuro, vai
lembrar de filtrar por `espaco_id`, o filtro é automático, no nível da
sessão do banco — o mesmo princípio de "deixar a ferramenta fazer o trabalho
mecânico" já usado neste projeto para o Alembic.

```python
# app/espaco.py (novo)
import contextvars
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

espaco_atual_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "espaco_atual", default=None
)

MODELOS_COM_ESPACO = (
    Ano, Conta, Categoria, Lancamento, GastoFixo, GastoFixoMensal,
    SaldoInicial, RegraCategorizacao, CorFormaPagamento, MetaPoupanca,
    Caixinha, FaturaMensal, ItemWishlist, CompraParcelada,
)

@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_espaco(estado):
    """Toda consulta SELECT contra um modelo com espaco_id só vê o espaço
    ativo da sessão atual. Sem isto, bastaria um router esquecer um filtro
    para vazar dado de um espaço pro outro."""
    if not estado.is_select:
        return
    espaco_id = espaco_atual_ctx.get()
    if espaco_id is None:
        return  # fora de requisição autenticada (scripts, testes) — sem filtro
    for modelo in MODELOS_COM_ESPACO:
        estado.statement = estado.statement.options(
            with_loader_criteria(modelo, lambda cls: cls.espaco_id == espaco_id)
        )

@event.listens_for(Session, "before_flush")
def _carimbar_espaco_em_novos(sessao, _contexto, _instancias):
    """Toda linha nova que ainda não tem espaco_id herda o espaço ativo —
    rede de segurança para quem esquecer de passar no router; não sobrescreve
    quem já definiu explicitamente (caso do `Ano`, que não tem de onde herdar)."""
    espaco_id = espaco_atual_ctx.get()
    if espaco_id is None:
        return
    for objeto in sessao.new:
        if isinstance(objeto, MODELOS_COM_ESPACO) and objeto.espaco_id is None:
            objeto.espaco_id = espaco_id
```

`usuario_atual` (em `deps.py`) passa a fixar `espaco_atual_ctx` no início de
toda requisição, a partir de `usuario.espaco_atual_id` — uma linha a mais na
função que já existe.

**Regra adicional, de schema:** `espaco_id` nunca é um campo aceito em
nenhum `*Criar`/`*Atualizar` exposto pela API — é sempre resolvido do
contexto da sessão (pelo mecanismo acima), nunca do que o cliente manda no
corpo da requisição. Isso fecha a possibilidade de alguém tentar "mover" um
registro para outro espaço forjando o campo num `PATCH`.

### Migração dos dados existentes

Uma migração Alembic, em uma única transação:

1. Cria a tabela `espacos`, insere uma linha (`nome="Kamilly"` ou o que ela
   preferir).
2. Cria `membros_espaco`, insere uma linha ligando o `Usuario` existente a
   esse espaço como `DONO`.
3. Adiciona `espaco_id` (NOT NULL, FK, indexado) em cada uma das catorze
   tabelas, com um `UPDATE` que preenche todas as linhas existentes com o
   id desse espaço único — nunca `NULL`able de passagem: a coluna já nasce
   obrigatória, porque todo dado que existe hoje tem, sim, um dono certo.
4. Define `usuarios.espaco_atual_id` para esse mesmo espaço.

### Exportar e apagar — os dois direitos da LGPD que a revisão anterior apontou em aberto

```ts
// GET /espacos/{id}/espaco_id}/exportar — qualquer membro
// Devolve um JSON com todos os anos, contas, lançamentos etc. daquele espaço.
```

`DELETE /auth/eu` (apagar a própria conta) — três casos:

- A pessoa é **dona de um espaço só dela** (sem outros membros): apaga o
  `Usuario` e o `Espaco` inteiro, de verdade — `ondelete=CASCADE` em
  `espaco_id` em toda tabela remove tudo. É literalmente isto que "direito
  ao esquecimento" pede; não é soft-delete aqui.
- A pessoa é **dona de um espaço com outros membros**: `409` — "Você é
  responsável pelo espaço 'X', que tem outras pessoas dentro. Transfira a
  responsabilidade ou remova os membros antes de apagar sua conta." Nunca
  apaga um espaço por baixo dos pés de quem ainda o usa.
- A pessoa é **só membro** (não dona) de outros espaços: sai desses
  espaços (remove a `MembroEspaco` dela) e apaga o próprio `Usuario`; o
  espaço e os dados continuam existindo para quem ficou.

Exige reautenticação (senha de novo no corpo da requisição) — é
irreversível, não deveria bastar uma sessão já aberta sequestrada.

## Consequências

- Migração grande, mas mecânica — catorze `ALTER TABLE ADD COLUMN`, um
  backfill, duas tabelas novas.
- **Toda rota que hoje confia em `obter_ano`/`obter_ano_editavel` (a grande
  maioria) fica protegida de graça** — o `Ano` que a dependência devolve já
  vem filtrado pelo espaço ativo; pedir o ano "2026" de um espaço que não é
  o seu simplesmente devolve 404, como se o ano não existisse.
- **Tarefa que não é automática:** auditar todo router e todo serviço
  procurando consulta que acesse uma das catorze tabelas **sem** passar
  pela sessão do SQLAlchemy comum (ex.: SQL cru — não encontrei nenhum
  hoje, mas é o tipo de coisa que precisa ser conferida de novo depois
  desta mudança) e qualquer lugar que construa um objeto novo sem passar
  pelo fluxo normal de `criar()` de um router (scripts administrativos,
  por exemplo, continuam fora do contexto de requisição — `scripts/
  criar_usuario.py` e afins precisam setar `espaco_id` manualmente, já que
  não há `espaco_atual_ctx` fora de uma requisição HTTP).
- **Critério de aceite inegociável antes de considerar isto pronto:** um
  teste que cria dois espaços com dados que colidem de propósito (ambos
  com um "Ano 2026", ambos com uma "Categoria Alimentação") e confere, para
  **cada** endpoint de leitura do sistema, que uma sessão do espaço A nunca
  vê uma linha do espaço B. Isto pesa mais que qualquer outro teste deste
  ADR.
- `routers/metas_poupanca.py::ativas()` hoje busca o `Ano` do ano corrente
  direto (`db.query(Ano).filter(Ano.ano == hoje.year)`), sem passar por
  `obter_ano` — continua funcionando porque `Ano` está em
  `MODELOS_COM_ESPACO` (o filtro da sessão pega de qualquer forma), mas é
  um exemplo concreto de por que o filtro não pode depender de todo router
  usar a mesma dependência.
- Scripts administrativos (`criar_usuario.py`) precisam saber a qual
  espaço vincular um usuário novo, ou criar um espaço próprio pra ele —
  mesma lógica do cadastro aberto (ADR-16), só que rodada manualmente.

## Alternativas consideradas

- **Isolar por `usuario_id` direto, sem o conceito de `Espaco`.** Foi a
  primeira ideia, descartada no momento em que a Kamilly confirmou que
  quer permitir contas compartilhadas — `usuario_id` direto não modela
  "duas pessoas, os mesmos dados" sem duplicar cada lançamento por pessoa
  (o que quebraria a ideia de ser a mesma informação).
- **Só as tabelas hoje globais ganham `espaco_id`; o resto confia no
  `Ano`.** Rejeitada pela razão já exposta na decisão: dois mecanismos de
  proteção em vez de um só aumentam a chance de alguém auditar o errado.
- **Filtrar por espaço manualmente em cada router**, sem o evento do
  SQLAlchemy. Rejeitada: exigiria lembrar de adicionar `.filter(espaco_id
  == ...)` em toda consulta nova, para sempre — exatamente o tipo de
  disciplina que falha silenciosamente um dia, e o custo de falhar aqui é
  alto demais pra depender só de disciplina.
- **Permissões graduadas por membro** (dono edita, membro só lê, etc.).
  Rejeitada por agora — não corresponde ao caso real pedido (casal
  dividindo controle financeiro igualmente); pode virar uma extensão futura
  se o uso real pedir.
