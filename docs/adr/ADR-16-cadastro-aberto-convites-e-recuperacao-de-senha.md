# ADR-16 — Cadastro aberto, convite para espaço compartilhado e recuperação de senha por e-mail

**Status:** proposto

## Contexto

Hoje (`routers/auth.py`) não existe cadastro pela API de propósito —
"usuários são criados pelo script `scripts/criar_usuario.py`... um app de
finanças pessoais publicado na internet não tem motivo para aceitar
cadastro aberto". Isso deixa de ser verdade quando o próprio objetivo é
várias pessoas poderem usar o sistema por conta própria, sem depender da
Kamilly rodar um comando pra cada uma.

A Kamilly confirmou que quer cadastro aberto, aceitando o custo que isso
traz (verificação de e-mail, pra não acumular conta falsa), e quer
recuperação de senha por e-mail — com o fluxo todo pronto, mas o **envio
de e-mail de verdade configurado depois** ("deixar um rascunho pronto").

Isto depende do ADR-15 (espaços financeiros) estar implementado primeiro —
todo cadastro novo cria um espaço, e todo convite vincula a um espaço
existente.

## Decisão

### Uma tabela só para "token de uso único ligado a um e-mail", reaproveitada em dois fluxos

Verificar e-mail e recuperar senha resolvem o mesmo problema estrutural:
confirmar que a pessoa controla aquele e-mail, através de um link de uso
único que expira. Uma tabela e um serviço só, não dois:

```python
class FinalidadeToken(str, enum.Enum):
    VERIFICACAO_EMAIL = "verificacao_email"
    REDEFINICAO_SENHA = "redefinicao_senha"

class TokenAcao(Base):
    __tablename__ = "tokens_acao"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    finalidade: Mapped[FinalidadeToken] = mapped_column(Enum(FinalidadeToken, native_enum=False))
    # Nunca o token puro — mesma razão de nunca guardar a senha puro (security.py).
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

O token enviado por e-mail é um valor aleatório (`secrets.token_urlsafe`,
já usado em `config.py`); só o **hash** dele (SHA-256 é suficiente aqui —
não é senha, é um valor aleatório de alta entropia, não precisa de bcrypt)
fica no banco, pelo mesmo motivo de nunca guardar segredo em texto puro.
Expiração curta: 30 minutos para redefinição de senha, 24 horas para
verificação de e-mail (menos urgente, mais tolerante a a pessoa não abrir
o e-mail na hora).

### Cadastro

```ts
// POST /auth/cadastro
interface CadastroCriar { email: string; senha: string; nome?: string; }
```

- Cria `Usuario` (`ativo=True`, `email_verificado=False` — campo novo).
- Cria um `Espaco` próprio (`nome` default: "Financeiro de {nome ou
  e-mail}"), vincula como `DONO` via `MembroEspaco`, define
  `espaco_atual_id` — **exceto** se existir um convite pendente pra esse
  e-mail (ver abaixo), caso em que entra no espaço convidado em vez de
  criar um novo.
- Gera `TokenAcao` de verificação, chama `enviar_email(...)` (ver seção de
  envio pendente).
- Loga a pessoa automaticamente — **não verificado não bloqueia uso**,
  mostra um aviso na interface ("confirme seu e-mail") sem impedir nada.
  Decisão deliberada: o e-mail não verificado é um risco só pra
  funcionalidades que dependem dele (recuperação de senha, convite) — não
  há razão pra travar o resto do app por isso, mesmo princípio de "não
  travar por dado incompleto" que `docs/REGRAS.md` já registra para outros
  casos.

### Convite para espaço compartilhado

```ts
// POST /espacos/{id}/convites — só DONO
interface ConviteCriar { email: string; }
// POST /convites/{token}/aceitar — pessoa já logada
```

```python
class ConviteEspaco(Base):
    __tablename__ = "convites_espaco"
    id: Mapped[int] = mapped_column(primary_key=True)
    espaco_id: Mapped[int] = mapped_column(ForeignKey("espacos.id", ondelete="CASCADE"))
    email_convidado: Mapped[str] = mapped_column(String(255), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    criado_por_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime]
    aceito_em: Mapped[datetime | None] = mapped_column(nullable=True)
```

Fluxo com duas entradas possíveis, pela mesma URL de convite
(`/convite/{token}` no frontend):

1. **Quem recebe já tem conta:** faz login (se não estiver) e aceita — cria
   `MembroEspaco(papel=MEMBRO)`, marca `aceito_em`.
2. **Quem recebe não tem conta:** a tela de convite leva ao cadastro
   normal, com o e-mail pré-preenchido e travado (não editável, tem que ser
   o e-mail convidado). Ao completar o cadastro, o backend encontra o
   convite pendente daquele e-mail automaticamente e vincula ao espaço
   convidado **em vez** de criar um espaço novo — esse é o desvio do fluxo
   padrão de cadastro mencionado na seção anterior.

Convite tratado como qualquer token: uso único, expira (7 dias — mais
tolerante que o de senha, porque convidar alguém pra um espaço financeiro
é uma decisão que a pessoa convidada pode levar alguns dias pra aceitar).

### Recuperação de senha

```ts
// POST /auth/esqueci-senha { email }
// Sempre responde sucesso genérico — mesma razão do login (ADR original):
// não revelar se o e-mail existe. Se existir, gera TokenAcao e envia e-mail.

// POST /auth/redefinir-senha { token, nova_senha }
// Valida hash + expiração + não usado (mesmas validações de sempre:
// mínimo 8 caracteres). Troca a senha, marca usado_em, invalida qualquer
// outro TokenAcao de redefinição pendente do mesmo usuário.
```

### O envio de e-mail de verdade é a única parte que fica pendente

```python
# app/services/email.py (novo)
def enviar_email(destinatario: str, assunto: str, link: str) -> None:
    """Envia um e-mail transacional (verificação, convite, recuperação de senha).

    Pendente: nenhum provedor configurado ainda (ver ADR-16). Até a
    Kamilly decidir e configurar um (Resend, SES, etc.), este envio só
    aparece no log do servidor — suficiente para testar o fluxo inteiro
    sem bloquear o resto da feature por uma decisão de infraestrutura que
    pode vir depois.
    """
    if not settings.email_provider_configurado:
        logging.info("E-mail pendente de envio real — %s: %s -> %s", assunto, destinatario, link)
        return
    ...  # integração real, quando o provedor for escolhido
```

Isto segue exatamente o precedente que já existe no código:
`Usuario.alertas_email_ativo` (ADR-06) é "o campo existe para a
preferência ter onde morar quando essa fase chegar... por enquanto ligá-lo
não faz nada". O mesmo raciocínio vale aqui — o fluxo inteiro (cadastro,
convite, recuperação) funciona de ponta a ponta nos testes e em
desenvolvimento (o link aparece no log, dá pra copiar e colar na mão), só
o envio de verdade por e-mail depende de uma conta num provedor que a
Kamilly ainda não escolheu.

`settings.email_provider_configurado` (um booleano simples, ou a própria
ausência de uma variável como `RESEND_API_KEY`) é o interruptor —
documentado em `.env.example`, igual o `SECRET_KEY` já é hoje.

## Consequências

- Migração: `usuarios.email_verificado` (boolean, default `false`),
  tabelas novas `tokens_acao` e `convites_espaco`.
- `UsuarioAtualizar` (schemas.py) e o comentário que diz "senha se muda
  pelo script de administração" ficam desatualizados — atualizar o
  comentário; a troca de senha self-service passa a ser o caminho normal,
  o script continua existindo como ferramenta de administração (resetar a
  senha de alguém que perdeu acesso ao e-mail, por exemplo).
- Tela de login (`routes/login.tsx`) ganha links "Criar conta" e "Esqueci
  minha senha"; duas telas novas no frontend (`/cadastro`,
  `/redefinir-senha`), e uma tela de convite (`/convite/$token`).
- Configurações (ou uma tela de "Espaço") ganha a lista de membros do
  espaço atual, botão de convidar (só visível pro dono) e o seletor de
  espaço (se a pessoa for membro de mais de um).
- Cadastro aberto **depende** do ADR-17 (limite de tentativas) estar
  implementado — um formulário de cadastro público sem nenhum limite é uma
  porta pra criação automatizada de contas em massa.

## Alternativas consideradas

- **Bloquear o uso até verificar o e-mail.** Rejeitada — adiciona atrito
  sem necessidade real: o e-mail não verificado só importa pras
  funcionalidades que dependem dele (recuperação, convite), que já lidam
  com isso sozinhas (recuperação de senha funciona independente de
  verificação — se o e-mail não for de quem diz ser, o link cai na caixa
  de quem é dono de verdade daquele e-mail, não é uma porta de entrada).
- **Tabelas separadas para token de verificação e de redefinição.**
  Rejeitada — são o mesmo problema (token de uso único, com expiração,
  ligado a um usuário); separar duplicaria o código de gerar, validar e
  expirar sem ganho real.
- **Esperar decidir o provedor de e-mail antes de implementar o resto do
  fluxo.** Rejeitada — foi literalmente o pedido da Kamilly ("configurar
  esse serviço de envio mais tarde, deixar um rascunho pronto"): a
  infraestrutura de envio é a única peça que pode esperar, o resto (banco,
  validação, telas) não depende de qual provedor for escolhido.
