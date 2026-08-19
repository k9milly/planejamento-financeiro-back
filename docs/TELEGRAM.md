# Lançamento rápido por Telegram

Manda uma mensagem tipo `15, brownie, mercado pago` para o bot, e ele cria o
lançamento na hora — com a data do envio, a conta reconhecida pelo texto e a
categoria sugerida pelas mesmas regras que você já ensinou na importação de
extrato.

## O formato da mensagem

```
valor, descrição, conta
```

Descrição e conta são **opcionais**. Só o valor é obrigatório, e precisa vir
primeiro.

| Você manda | Vira |
| --- | --- |
| `15, brownie, mercado pago` | R$ 15,00 · brownie · Mercado Pago |
| `15 reais, brownie, cartao credito mercado pago` | mesma coisa — a conta é reconhecida mesmo com texto solto ao redor |
| `15, brownie` | conta padrão (a primeira cadastrada) |
| `15` | sem descrição, conta padrão |
| `15,50, brownie` | R$ 15,50 — o valor é lido antes de qualquer vírgula de campo, então decimal com vírgula não quebra |

**Só cria saídas (gastos).** Entradas, transferências entre contas e outros
tipos continuam pelo app — essa via é propositalmente simples, para caber
numa mensagem de celular sem ambiguidade.

Se a conta que você mencionou não for reconhecida, o bot avisa na resposta e
usa a conta padrão mesmo assim — o lançamento não fica perdido, só talvez na
conta errada, e dá pra corrigir depois pelo app.

Se o ano da mensagem ainda não existir no app (ou estiver arquivado), o bot
recusa e explica — nada é criado silenciosamente errado.

---

## Configurando pela primeira vez

### 1. Criar o bot

No Telegram, procure por **@BotFather** e mande:

```
/newbot
```

Escolha um nome (aparece para você) e um "username" (precisa terminar em
`bot`, ex.: `planejamento_financeiro_bot`). Ao final, o BotFather te dá um
**token** — uma linha tipo `123456:ABC-...`. Copie e guarde; é uma senha do
seu bot.

### 2. Descobrir o seu chat_id

Mande **qualquer mensagem** para o bot que você acabou de criar (ele ainda
não vai responder nada — sem problema).

Depois, no navegador, acesse (trocando `SEU_TOKEN` pelo token do passo 1):

```
https://api.telegram.org/botSEU_TOKEN/getUpdates
```

Na resposta, procure por `"chat":{"id":` — o número ali é o seu `chat_id`.
Anote.

### 3. Gerar o segredo do webhook

No terminal, na pasta `backend`:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copie a linha que aparecer — esse é um segredo novo, diferente da
`SECRET_KEY` da sessão. Ele garante que só o Telegram (e mais ninguém que
descobrisse a URL) consiga mandar lançamentos.

### 4. Configurar os três segredos no Fly

```powershell
flyctl secrets set TELEGRAM_BOT_TOKEN="o-token-do-passo-1"
```

```powershell
flyctl secrets set TELEGRAM_WEBHOOK_SECRET="o-segredo-do-passo-3"
```

```powershell
flyctl secrets set TELEGRAM_CHAT_ID="o-numero-do-passo-2"
```

Cada `secrets set` já reinicia a aplicação sozinho.

### 5. Registrar o webhook no Telegram

Isso avisa o Telegram para onde mandar as mensagens. Rode (trocando
`SEU_TOKEN` e `SEU_SEGREDO` pelos valores dos passos 1 e 3):

```powershell
curl -UseBasicParsing -Method Post "https://api.telegram.org/botSEU_TOKEN/setWebhook" -Body @{url="https://planejamento-financeiro.fly.dev/webhooks/telegram"; secret_token="SEU_SEGREDO"}
```

Deve responder algo como `{"ok":true,"result":true,"description":"Webhook was set"}`.

### 6. Testar

Manda `15, teste` para o bot no Telegram. Ele deve responder confirmando o
lançamento em poucos segundos, e o gasto aparece no app na hora.

---

## Se algo não funcionar

**O bot não responde nada:** confira se os três segredos foram mesmo salvos
(`flyctl secrets list` mostra os nomes, nunca os valores) e se o `setWebhook`
do passo 5 respondeu `"ok":true`.

**Erro `403` ao rodar o `setWebhook`:** o token do bot está errado — confira
se copiou a linha inteira do BotFather.

**O bot diz "não reconheci a conta":** o nome que você escreveu não bate com
nenhuma conta cadastrada no app. Confira o nome exato em **Contas**, na tela
principal.

**Quero trocar o segredo do webhook** (por exemplo, se suspeitar que
vazou): gere um novo no passo 3, atualize com `flyctl secrets set
TELEGRAM_WEBHOOK_SECRET=...`, e repita o `setWebhook` do passo 5 com o valor
novo — os dois lados precisam combinar.
