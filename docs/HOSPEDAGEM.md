# Publicando na internet

Guia passo a passo. Você cria as contas e roda os comandos; nenhuma senha ou
chave precisa sair da sua máquina.

**Arquitetura publicada:**

```
Celular / PC
     │  HTTPS
     ▼
Netlify ──────────► Fly.io (São Paulo) ──────► Neon (São Paulo)
frontend estático     API FastAPI              Postgres
```

Por que São Paulo nos dois: cada consulta ao banco é uma ida e volta. Com o
servidor em Virgínia e o banco em São Paulo, toda tela somaria centenas de
milissegundos à toa.

---

## Antes de começar

Você vai precisar de:

- Conta no [Neon](https://neon.com) (gratuita)
- Conta no [Fly.io](https://fly.io) (pede cartão; o custo fica em torno de
  US$ 1–2 por mês com hibernação ligada)
- Acesso ao Netlify (ou qualquer host de site estático)

---

## 1. Criar o banco no Neon

1. Crie um projeto.
2. Em **Region**, escolha **AWS South America (São Paulo)** — `aws-sa-east-1`.
   Isso não dá para mudar depois sem recriar o projeto.
3. Copie a *connection string*. Ela se parece com:

   ```
   postgresql://usuario:senha@ep-algo.sa-east-1.aws.neon.tech/neondb?sslmode=require
   ```

4. **Troque o começo** `postgresql://` por `postgresql+psycopg://`. É o que diz
   ao SQLAlchemy qual driver usar. O resto fica igual.

Guarde essa URL: ela é uma senha de banco.

## 2. Criar o schema no Neon

Na sua máquina, dentro de `backend`:

```bash
$env:DATABASE_URL="postgresql+psycopg://...a-sua-url..."
.venv\Scripts\alembic.exe upgrade head
```

Isso cria as tabelas vazias. Confira no painel do Neon que elas apareceram.

## 3. Copiar seus dados

Ainda com `DATABASE_URL` apontando para o Neon, **primeiro simule**:

```bash
.venv\Scripts\python.exe -m scripts.copiar_para_postgres "postgresql+psycopg://...' --simular
```

Confira os números. Depois rode sem `--simular`.

O script se recusa a copiar sobre um banco que já tenha dados, para não
misturar dois históricos. Ao final ele ajusta os contadores de id do Postgres —
sem isso, o primeiro lançamento novo tentaria reusar um id existente e falharia.

Limpe a variável depois, para não continuar apontando para produção:

```bash
$env:DATABASE_URL=$null
```

## 4. Publicar o backend no Fly.io

Instale o CLI e faça login (abre o navegador):

```bash
winget install --id Fly.Flyctl
```

```bash
fly auth login
```

Na pasta `backend`, crie o app **sem publicar ainda**:

```bash
fly launch --no-deploy --region gru
```

Aceite reaproveitar o `fly.toml` existente quando ele perguntar. Se o nome
`planejamento-financeiro` já estiver em uso, ele sugere outro — anote qual.

Agora os segredos. Eles **não** vão para o `fly.toml`, que é versionado:

```bash
fly secrets set DATABASE_URL="postgresql+psycopg://...a-sua-url..."
```

Gere a chave de sessão e defina:

```bash
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
fly secrets set SECRET_KEY="a-linha-que-apareceu"
```

Publique:

```bash
fly deploy
```

Ao final ele mostra a URL, algo como `https://planejamento-financeiro.fly.dev`.
Teste:

```bash
curl https://planejamento-financeiro.fly.dev/saude
```

Deve responder `{"status":"ok"}`.

## 5. Publicar o frontend no Netlify

O frontend precisa saber onde está a API. Na pasta `frontend`, crie
`.env.production`:

```
VITE_API_URL=https://planejamento-financeiro.fly.dev
```

No Netlify, conecte o repositório e configure:

| Campo | Valor |
| --- | --- |
| Base directory | `frontend` |
| Build command | `npm run build` |
| Publish directory | `frontend/dist` |

Anote o endereço final, ex.: `https://seu-app.netlify.app`.

## 6. Liberar o frontend no CORS

Por padrão a API só aceita chamadas de `localhost`. Sem este passo, o site
publicado carrega mas nenhuma informação aparece.

```bash
fly secrets set CORS_ORIGINS='["https://seu-app.netlify.app"]'
```

O formato é uma lista JSON. Nunca use `"*"`: com sessão habilitada, isso
permitiria que qualquer site fizesse pedidos em seu nome.

## 7. Conferir

Abra o endereço do Netlify no celular. Você deve ver a tela de login, entrar
com o usuário que criou, e encontrar seus dados.

Adicione à tela de início pelo menu do navegador para ter um ícone como o de
um aplicativo.

---

## Manutenção

**Publicar uma mudança:**

```bash
fly deploy
```

O container roda `alembic upgrade head` antes de subir. Se a migração falhar,
o deploy é abortado em vez de servir com o schema errado.

**Ver o que está acontecendo:**

```bash
fly logs
```

**Backup do banco:** o Neon guarda um histórico que permite voltar o banco a um
momento anterior. Vale conferir no painel por quantos dias, porque isso varia
conforme o plano.

**Trocar a chave de sessão** (se suspeitar que vazou):

```bash
fly secrets set SECRET_KEY="uma-nova-chave"
```

Isso desloga todas as sessões imediatamente.

---

## Alternativa: sem publicar nada

Se um dia preferir não expor na internet, dá para rodar tudo no seu PC e
acessar do celular por [Tailscale](https://tailscale.com) — uma rede privada
entre seus aparelhos. Custo zero e nada fica público; a limitação é que o PC
precisa estar ligado.
