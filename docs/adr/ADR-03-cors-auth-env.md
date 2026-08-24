# ADR-03 — Política de CORS, autenticação e variáveis de ambiente

**Status:** proposto

## Contexto

Os dois repositórios já têm, cada um, metade do mecanismo de autenticação
pronto — só nunca foram conectados um ao outro:

- **Backend**: `CORSMiddleware` já configurado em `main.py`
  (`allow_origins=settings.cors_origins, allow_credentials=True,
  allow_methods=["*"], allow_headers=["*"]`), lendo de `CORS_ORIGINS` no
  `.env` (`app/config.py`), com default
  `["http://localhost:5173", "http://127.0.0.1:5173"]`. Autenticação é JWT
  sem estado (`app/security.py`): login devolve um token (`Bearer`), toda
  rota de dado exige `Authorization: Bearer <token>` (`app/deps.py`,
  `usuario_atual`), validade de 30 dias por padrão
  (`token_expira_horas`). **Não há cookie envolvido em nenhum momento** —
  é Bearer puro, guardado e enviado pelo cliente.
- **Frontend**: hoje não tem nenhum cliente HTTP, nenhum `.env`, e nenhum
  lugar guardando token — é 100% mock, sem rede.

Dois detalhes concretos, encontrados na leitura dos arquivos, mudam a forma
como esta ADR precisa ser escrita em vez de copiar a política do outro
repositório sem revisar:

1. **`http://localhost:5173` é a porta do Vite puro, não do TanStack
   Start.** O frontend novo roda `vite dev` através do plugin
   `@lovable.dev/vite-tanstack-config`, que pode escolher outra porta
   (a configuração está fora do repositório, dentro do pacote da Lovable).
   O `CORS_ORIGINS` do backend precisa ser conferido contra a porta real do
   `npm run dev` deste projeto especificamente, não assumido igual ao app
   antigo.
2. **`allow_credentials=True` hoje não tem função, porque não há cookie.**
   Essa flag existe para permitir que o navegador envie cookies/credenciais
   em requisições cross-origin; com autenticação 100% via header
   `Authorization`, ela não faz diferença nenhuma no fluxo atual — mas
   também não atrapalha (é inofensiva com `allow_origins` explícito, que já
   é o caso aqui; só seria um problema se algum dia migrasse para
   `allow_origins=["*"]`, o que o CORS do navegador já proíbe combinar com
   `allow_credentials=True`). Mantida como está, documentada aqui para não
   ser vista como um mistério por quem ler o código depois.

## Decisão

### CORS

`CORS_ORIGINS` no `.env` do backend passa a listar, além do que já usa
(dev local do repo antigo, se ainda estiver em uso), a origem de
desenvolvimento **e** a origem de produção do novo frontend:

```
CORS_ORIGINS=http://localhost:5173,https://<domínio-de-preview-ou-produção-do-lovable>
```

A porta de dev exata deve ser confirmada rodando `npm run dev` no
repositório do frontend (Parte 3, backend, primeira tarefa) — não
assumida. Em produção, se o frontend for publicado num domínio próprio
depois (fora do domínio padrão do Lovable), o valor precisa ser atualizado
no ambiente do backend (Fly.io: `flyctl secrets set CORS_ORIGINS=...`) —
igual já é feito hoje para o app antigo.

### Autenticação

O frontend reutiliza o mecanismo já pronto no backend, sem mudança de
protocolo:

1. Tela de login chama `POST /auth/login` com `{ email, senha }`.
2. Guarda o `token` recebido.
3. Toda chamada subsequente à API manda `Authorization: Bearer <token>`.
4. Na abertura do app, antes de renderizar qualquer tela de dado, chama
   `GET /auth/eu` — `401` significa token ausente/expirado/inválido, e a
   tela de login é mostrada; qualquer outra resposta segue para o app.
5. Não há refresh token nem renovação silenciosa — o backend não implementa
   isso (decisão já tomada no ADR de segurança do repo antigo: trocar a
   `secret_key` é o único "botão de pânico"). Um `401` em qualquer chamada,
   a qualquer momento, desloga e volta para a tela de login.

**Onde o token fica guardado no navegador: `localStorage`.** Documentando a
troca conscientemente, porque toda escolha de guardar um token no cliente
tem um trade-off: `localStorage` é acessível por qualquer script rodando na
página (risco em caso de XSS), mas é a opção compatível com o backend atual
(que não emite cookie `httpOnly` — mudar isso seria alterar o mecanismo de
auth do backend, fora do escopo desta integração) e é consistente com o
resto do projeto, que já guarda preferências (tema, modo visual) da mesma
forma. Mitigação real, não cosmética: o projeto não deve incluir nenhuma
biblioteca de terceiros que injete script arbitrário na página (analytics
de terceiros, widgets de chat, etc.) sem revisão — é essa superfície,
não a escolha de `localStorage` em si, que decide o risco de XSS na
prática.

### Variáveis de ambiente do frontend

TanStack Start (via Vite) expõe ao navegador só variáveis prefixadas
`VITE_` — igual a qualquer app Vite. Um único valor é necessário:

```
# .env (frontend, não versionado)
VITE_API_URL=http://localhost:8000
```

Em produção, o valor aponta para a URL pública do backend no Fly.io
(`https://planejamento-financeiro.fly.dev`, ou o domínio configurado —
confirmar o valor real no painel do Fly.io antes de publicar, não assumir).
Um `.env.example` documentado deve ser adicionado ao repositório do
frontend, no mesmo espírito do que já existe em `backend/.env.example`.

## Consequências

- Nenhuma mudança de mecanismo no backend — CORS e JWT já existem prontos;
  a única ação do lado backend é atualizar a lista de origens permitidas.
- O frontend ganha, pela primeira vez, um `.env`/`.env.example` e uma
  camada de cliente HTTP que lê `VITE_API_URL` (detalhada na Parte 3).
- Um `401` em qualquer chamada precisa de tratamento centralizado (não em
  cada tela) — o interceptor do cliente HTTP (Axios) ou o `onError` global
  do `QueryClient` (ver ADR-02) é o lugar certo: limpar o token e redirecionar
  para o login, uma vez só, não duplicado em cada `useQuery`.

## Alternativas consideradas

- **Cookie `httpOnly` em vez de Bearer em `localStorage`.** Mais resistente
  a XSS, mas exige mudar o backend (emitir `Set-Cookie`, tratar CSRF já que
  TanStack Start inclusive já tem `createCsrfMiddleware` pronto para server
  functions — só não para chamadas de API externas como esta) e mudar CORS
  para `allow_credentials` de verdade. Rejeitada para esta rodada por
  escopo — é uma mudança de arquitetura de autenticação do backend, não uma
  integração de frontend existente; fica registrada como opção futura se o
  risco de XSS acima deixar de ser aceitável.
- **`sessionStorage` em vez de `localStorage`.** Derrubaria a sessão a cada
  fechar de aba, incompatível com "sessão longa de propósito" já decidida
  no backend (`token_expira_horas`, pensada para uso diário sem relogar
  toda hora) — rejeitada por contradizer uma decisão já tomada do lado da
  API.
