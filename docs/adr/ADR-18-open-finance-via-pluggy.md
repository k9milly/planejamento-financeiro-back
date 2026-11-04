# ADR-18 — Open finance via Pluggy

**Status:** proposto — o passo 1 (connect token) já está escrito e testado;
o resto deste documento é desenho, não código.

## Contexto

Hoje a única forma de o dinheiro entrar no app sem digitação é a importação
de arquivo: o usuário baixa o extrato no banco, escolhe o arquivo, revisa a
prévia e confirma (`ADR-08` para OFX/CSV/XLSX, `ADR-12` para PDF). Funciona,
e vai continuar funcionando — mas o passo manual é diário: baixar o extrato
do Mercado Pago em PDF toda semana cansa, e quem cansa deixa de lançar.

A Kamilly pediu **open finance**: o banco manda os dados, em vez de a pessoa
buscar.

### O que "open finance" significa aqui, com honestidade

O Open Finance Brasil é regulado pelo Banco Central. Para puxar dados de
outra instituição **em nome próprio** é preciso ser instituição autorizada e
registrada no diretório de participantes — um aplicativo pessoal não é, nem
vai ser.

O caminho real para um app pequeno é usar um **agregador** que já é
participante autorizado e revende o acesso por API. A Pluggy é um desses. A
consequência prática de escolher esse caminho:

- O consentimento é dado pelo usuário no ambiente do **banco dele**, e quem
  aparece como quem recebe o dado é a Pluggy, não este app.
- Nós nunca vemos senha de banco nem tocamos no fluxo de consentimento. Quem
  conduz é o widget da Pluggy (o *Pluggy Connect*).
- Fica uma dependência de terceiro no caminho de um dado sensível, e um custo
  por conexão ativa. É o preço de não ser banco.

### Dado real não é um interruptor, é uma aprovação

Conferido no painel da Pluggy em 04/11/2026, com a conta já criada — não
deduzido da documentação:

Uma aplicação nova nasce em **sandbox**, e conectar conta real de verdade é
um pedido à parte ("Testar com dados reais" → "Liberar dados reais"). O
acesso à produção tem três etapas obrigatórias, e uma quarta ao lado:

1. personalizar a aplicação (logo/cor do widget);
2. **conectar um item demo** — validar a integração ponta a ponta;
3. **registrar webhooks** num endpoint **não-localhost**, cobrindo
   `item/created`, `item/updated`, `transactions/created`,
   `transactions/updated` e `transactions/deleted` (ou o evento `all`);
4. **due diligence**: "informações da empresa e do representante legal para
   revisão de conformidade".

Duas consequências que mudam este ADR:

**O webhook deixa de ser fase tardia e vira pré-requisito.** Estava planejado
como fase 3, confortavelmente depois das tabelas. Não dá: sem endpoint
público registrado, a conta não sai do sandbox. O backend já está no Fly com
URL pública, então o obstáculo é só de ordem, não de infraestrutura.

**A due diligence pode ser intransponível para um app pessoal.** Pedir
"empresa" e "representante legal" sugere CNPJ. Se for obrigatório, o dado
real do Mercado Pago da Kamilly **nunca** sai do sandbox, e todo o código das
fases 2 a 5 fica sendo exercício. Isto precisa ser perguntado à Pluggy
**antes** de a fase 2 começar — é a pergunta mais barata e mais decisiva
desta integração, e está registrada aqui para não ser descoberta depois de
pronta.

### Qual via, para quais bancos

Pela documentação deles (não pelo painel, então confirmar ao conectar): o
Mercado Pago existe nas **duas** vias. Por Open Finance (pessoa física e
jurídica) e por conector direto — este último só pessoa física, trazendo
identidade, contas, transações e atualização automática, mas **não** cartão
de crédito.

A preferência é **Open Finance**, e o motivo não é técnico: no conector
direto o usuário digita login e senha do banco dentro do widget; no Open
Finance ele consente no ambiente do próprio banco. O custo da preferência é o
consentimento expirar (ver fase 5).

### Por que não dá para adivinhar a API deles

O exemplo de código que circulava para esta integração usava
`from pluggy_sdk import PluggyClient` e `pluggy.create_connect_token(...)`.
Baixei o SDK oficial e li: **a classe `PluggyClient` não existe em nenhum
arquivo**, nem o método `create_connect_token`. Os nomes reais são
`AuthApi.auth_create` e `AuthApi.connect_token_create`, e o `clientUserId`
vai **dentro de `options`**, não no corpo raiz.

Fica registrado porque é a razão de cada forma de requisição neste ADR vir
com a anotação de onde foi conferida. Um exemplo inventado que compila dá um
erro 400 difícil de entender seis meses depois.

Aviso de nome: o pacote `pluggy` que aparece instalado no projeto **não é**
esta Pluggy — é o sistema de plugins do pytest. Projetos sem nenhuma
relação, nomes iguais.

## Decisão

### 1. Uma credencial só, e ela nunca sai do servidor

Não existem "credenciais de sandbox" separadas — este documento chegou a
dizer isso numa versão anterior, e estava errado. A aplicação tem **um**
`clientId` e **um** `clientSecret`, e a URL é sempre `https://api.pluggy.ai`.
O sandbox é um **conector falso** ("Pluggy Bank"), que o widget mostra quando
o frontend passa `includeSandbox: true`. O que separa teste de produção é
qual banco se escolhe na tela, mais a liberação descrita acima — não a chave.

O `clientSecret` aparece **uma única vez**, na criação da aplicação no painel.

O `clientId` e o `clientSecret` ficam em variável de ambiente
(`PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET`), lidos por `app/config.py`,
nunca no repositório, e em produção via `flyctl secrets set`. Eles valem para
**toda** a base de usuários da aplicação: vazar um deles não é vazar um
extrato, é vazar o acesso a todos.

A única coisa que atravessa para o navegador é o **connect token**: curto,
descartável, e serve apenas para abrir o widget. Ele não lê dado nenhum.

```
POST /auth           {clientId, clientSecret}   -> {apiKey}   (vale 2h)
POST /connect_token  {options: {clientUserId}}  -> {accessToken}
```

Conferido lendo o SDK oficial. A `apiKey` autentica a segunda chamada no
cabeçalho `X-API-KEY`, e **não é guardada**: pedir connect token é raro (uma
vez por conexão de banco), e um cache traria invalidação para manter em troca
de economizar uma requisição.

**Implicação para o frontend:** não existe nada a configurar do lado dele.
Ele chama `POST /openfinance/connect-token`, recebe `{access_token}` e passa
isso ao widget. Se a instalação não tiver credenciais, a resposta é `503` com
mensagem — a tela deve esconder o botão de conectar banco, não quebrar.

### 2. A conexão pertence ao espaço, não à pessoa

O `clientUserId` mandado à Pluggy é `espaco-{id}`, não `usuario-{id}`.

É a consequência direta do `ADR-15`: dado financeiro pertence ao espaço, e um
casal que divide o controle divide também o banco conectado. Se fosse por
usuário, a conexão sumiria da tela do outro membro e cada um teria de
conectar o mesmo banco de novo — duas conexões pagas para o mesmo extrato,
além do dado aparecendo duplicado.

Quem ainda não escolheu espaço recebe `409`: sem espaço não há onde o
dinheiro entrar depois, e deixar conectar aqui só adiaria o erro para um
ponto bem pior (depois de o usuário já ter autorizado no banco).

### 3. A conexão vira uma linha nossa (`ConexaoBancaria`)

Depois do widget, a Pluggy cria um **item**: a conexão com aquele banco,
identificada por um `itemId`. Precisamos guardar esse identificador, senão
não há como saber que o webhook que chegou é de um espaço nosso.

```python
class ConexaoBancaria(Base, ComEspaco):
    """Um banco conectado por open finance, do ponto de vista do app.

    Não guarda credencial de banco nenhuma: só o identificador do item na
    Pluggy e o bastante para mostrar na tela e saber quando pedir renovação.
    """

    __tablename__ = "conexoes_bancarias"
    __table_args__ = (
        UniqueConstraint("espaco_id", "item_id", name="uq_conexao_por_espaco"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instituicao: Mapped[str] = mapped_column(String(80), nullable=False)
    situacao: Mapped[str] = mapped_column(String(30), nullable=False)
    # Quando o consentimento expira (open finance: até 12 meses). Nulo
    # enquanto a Pluggy não informar.
    consentimento_expira_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    sincronizado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Herda `ComEspaco`, então entra no isolamento automático do `ADR-15` sem mais
nenhuma linha — e o `DELETE /auth/eu` já a apaga junto com o espaço. Apagar a
linha aqui **não** cancela o item na Pluggy: isso é uma chamada à API deles,
e precisa ser feita de propósito (ver consequências).

### 4. Conta da Pluggy ↔ `Conta` nossa: ligação explícita, escolhida pelo usuário

Um item traz uma ou mais contas (conta corrente, cartão). Nossas `Conta`s já
existem, com nome escolhido pela Kamilly ("Nubank", "Mercado Pago"), cor e
ordem. Casar por nome seria adivinhação.

```python
class ContaConectada(Base, ComEspaco):
    __tablename__ = "contas_conectadas"
    __table_args__ = (
        UniqueConstraint("espaco_id", "account_id", name="uq_conta_conectada"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conexao_id: Mapped[int] = mapped_column(
        ForeignKey("conexoes_bancarias.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conta_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id", ondelete="SET NULL"), nullable=True
    )
    descricao_banco: Mapped[str] = mapped_column(String(120), nullable=False)
```

`conta_id` nulo significa "a Pluggy me oferece esta conta e ninguém disse
ainda o que fazer com ela" — estado legítimo, não erro: dá para conectar o
banco e decidir depois, e dá para ignorar de propósito uma conta que não
interessa. Transação de conta não ligada não entra em prévia nenhuma.

`ON DELETE SET NULL` em `conta_id`: apagar uma `Conta` não deve apagar a
conexão — o usuário pode querer reapontar para outra conta.

### 5. Webhook é aviso, nunca fonte de dado

A Pluggy avisa por webhook quando há transação nova. O endpoint é
necessariamente público (não há sessão de usuário num webhook), e isso é a
parte mais sensível desta integração: um endpoint público que grava dinheiro
é um convite.

**A decisão é não gravar nada do corpo do webhook.** O corpo é tratado como
um aviso sem conteúdo: "o item X mudou". A partir daí o backend:

1. Confere que o `itemId` existe em `conexoes_bancarias`. Se não existe,
   responde `200` e ignora — não é nosso.
2. **Busca** as transações na Pluggy, autenticando com as nossas credenciais.
   O dado que vale é o que veio dessa busca, não o que chegou no POST.
3. Responde `200` depressa. Webhook que demora é webhook reenviado.

Com isso, o pior que um POST forjado consegue é nos fazer consultar a Pluggy
à toa — não injetar um lançamento. A URL ainda leva um segredo no caminho
(`/openfinance/webhook/{segredo}`, de variável de ambiente) para encarecer
esse incômodo, mas o segredo é a segunda linha de defesa, não a primeira:
a primeira é não confiar no corpo.

### 6. As transações desaguam no fluxo de importação que já existe

Esta é a decisão central, e vale escrever por extenso **o que não vai ser
feito**: não existirá um caminho paralelo que grava `Lancamento`
automaticamente.

A transação da Pluggy vira uma `TransacaoExtrato` — a mesma `dataclass` que
`ler_ofx`, `ler_csv`, `ler_xlsx` e `ler_pdf` devolvem — e entra na prévia
existente. Com isso herda, sem código novo:

- deduplicação por identificador (`fitid`);
- detecção de "parece repetido" (mesma data e valor, outra origem) — que
  passa a importar de verdade, porque agora a mesma transação pode chegar
  pelo PDF e pela Pluggy;
- sugestão de categoria pelas `RegraCategorizacao`;
- a confirmação em duas etapas, com o usuário decidindo tipo, conta,
  categoria e caixinha;
- a validação de ano, de coerência e de conta compatível.

O `fitid` passa a ser o id da transação na Pluggy. Isso é **melhor** do que
o que os arquivos dão: é estável e vem do banco, então não precisa do
`identificador_sintetico` (data + valor + descrição) que CSV e PDF exigem.

Por que não gravar sozinho, já que o dado é confiável? Porque o dado é
confiável e a **classificação** não. O `ADR-08` já tinha fechado isso: um Pix
recebido pode ser salário ou devolução de um amigo, e uma transferência para
a poupança parece uma saída comum. Automatizar a gravação não economizaria a
revisão — só tiraria a chance de revisar antes.

O que muda na experiência é o que importava: o arquivo sai da história. A
tela de revisão deixa de ser "baixe o extrato, escolha o arquivo, revise" e
passa a ser "tem 7 transações novas para revisar".

### 7. Nada de iniciação de pagamento

A integração é somente leitura. A Pluggy também oferece iniciação de
pagamento (Pix) e isso fica **fora de escopo por decisão, não por falta de
tempo**: um app de planejamento pessoal que também move dinheiro tem um
perfil de risco completamente diferente, e nada no `ADR-01`..`ADR-17` foi
desenhado com isso em mente.

## Fases

A ordem mudou depois de olhar o painel: o webhook virou fase 2, porque é
exigência para a conta sair do sandbox.

| Fase | O que entra | Estado |
| --- | --- | --- |
| 1 | `POST /openfinance/connect-token`, credenciais em ambiente, erros `409`/`502`/`503` | escrito e testado, aguardando commit |
| 2 | Webhook público como aviso, respondendo `200` aos cinco eventos exigidos | a fazer |
| 3 | `ConexaoBancaria`, `ContaConectada`, migração, rotas de listar/apontar conta/desconectar | a fazer |
| 4 | `TransacaoExtrato` a partir da Pluggy, entrando na prévia existente | a fazer |
| 5 | Renovação de consentimento (widget em modo *update*) e aviso de expiração | a fazer |

**A pergunta que vem antes da fase 2:** se a due diligence exigir CNPJ, o
dado real nunca é liberado e as fases 2 a 5 não têm destino. Perguntar isso à
Pluggy custa uma mensagem e economiza o trabalho inteiro.

Respondida essa, a fase 2 em diante é escrita contra o **conector sandbox**
(`Pluggy Bank`), que devolve dado sintético com a mesma estrutura de campos da
produção. É o que permite mapear item, conta e transação sem tocar no dinheiro
de verdade de ninguém — e, de quebra, sem que um teste de importação acabe
gravando lançamento no espaço real da Kamilly.

Enquanto nada disso acontece, a fase 1 fica no ar devolvendo `503` em
instalação sem credencial — de propósito, para quem não usa open finance
continuar importando por arquivo normalmente.

## Consequências

- Uma dependência externa no caminho de um dado sensível, e um custo por
  conexão ativa. Mitigado em parte pela importação por arquivo continuar
  existindo: se a Pluggy sair do ar, encarecer ou mudar, o app não para.
- Migração nova na fase 3 (duas tabelas).
- Um endpoint público novo (webhook) na fase 2. A revisão de segurança e o
  `ADR-17` (limite de tentativas) devem considerá-lo: ele não autentica
  usuário, então o limitador por IP vale para ele também.
- Apagar uma `ConexaoBancaria` no nosso banco não cancela o item na Pluggy.
  A rota de desconectar precisa chamar a API deles **antes** de apagar a
  linha, e tratar o caso de a chamada falhar — apagar a nossa linha e deixar
  o item vivo é continuar pagando por uma conexão que ninguém vê, e manter
  dado do banco fluindo para um agregador sem que ninguém esteja olhando.
  É o pior defeito possível desta integração, e por isso está escrito aqui e
  não descoberto depois.
- `httpx` passou de dependência de teste a dependência de produção. O SDK
  oficial da Pluggy foi descartado na fase 1: são 3,2 MB em 309 arquivos
  cobrindo a API inteira (boletos, Pix automático, investimentos) para usar
  **duas** chamadas, e traria `urllib3` e `python-dateutil` junto. É a mesma
  conta que o `ADR-12` fez ao escolher `pypdf` em vez de `pdfplumber`.
- O consentimento do open finance expira (até 12 meses). Sem a fase 5, a
  conexão simplesmente para de trazer dado um dia, em silêncio. Enquanto a
  fase 5 não existir, isso é um defeito conhecido, não uma surpresa.
