# ADR-04 — Hospedagem do frontend: Cloudflare Workers

**Status:** aceito

## Contexto

Com a separação em dois repositórios, o `planejamento-financeiro-front`
precisa de uma hospedagem própria — antes, quando front e back moravam no
mesmo repositório do projeto original, `docs/HOSPEDAGEM.md` (ainda presente
no repo do back, como registro histórico) descrevia Netlify servindo os
arquivos estáticos do Vite puro. Esse guia não se aplica mais: o frontend
novo, gerado pela Lovable, é **TanStack Start** — tem renderização no
servidor (`src/server.ts`, `src/start.ts`, `createCsrfMiddleware` para
server functions) — não um SPA que vira uma pasta de arquivos estáticos.

Três caminhos foram avaliados, cada um com uma implicação técnica real (não
só de preferência):

1. **Netlify, com o plugin oficial (`@netlify/vite-plugin-tanstack-start`
   + `netlify.toml`).** Tecnicamente documentado e suportado pelo Netlify.
   O problema é específico deste repositório: o `vite.config.ts` é
   inteiramente gerenciado pelo pacote da própria Lovable
   (`@lovable.dev/vite-tanstack-config`), que já registra `tanstackStart()`,
   `nitro()` e outros plugins por conta própria — com um aviso explícito no
   topo do arquivo dizendo para não adicionar esses plugins manualmente, sob
   risco do app quebrar com plugins duplicados. Encaixar um plugin de build
   adicional (o do Netlify) dentro desse wrapper é uma combinação não
   testada, com risco real de conflito — e um risco que se repete a cada
   sincronização que a Lovable fizer de volta para o repositório.
2. **Cloudflare Workers.** O próprio pacote da Lovable já usa o preset
   `cloudflare-module` do Nitro como padrão (`nitro() defaults to the
   cloudflare-module preset` — ver a documentação de tipos do pacote,
   `LovableViteTanstackOptions`). Ou seja: não é preciso mudar nada no
   `vite.config.ts` — o build já produz a saída certa para esta plataforma
   por padrão, porque é para isso que o template da Lovable foi construído.
3. **Hospedagem própria da Lovable (`*.lovable.app` + domínio
   customizado).** Zero esforço de configuração — publicar é um botão
   dentro do editor. Mas domínio próprio exige plano pago da Lovable
   especificamente para isso, redirecionamento entre domínios é só 302
   temporário (não 301 permanente), e há menos controle de infraestrutura
   (variáveis de ambiente, logs) do que nas outras duas opções.

## Decisão

**Cloudflare Workers**, conectado via Git (Workers Builds) — não pelo
plugin `@cloudflare/vite-plugin` nem por um `wrangler.jsonc` escrito à mão.
O fluxo: conectar o repositório `planejamento-financeiro-front` pelo
painel do Cloudflare (Workers & Pages → Create → Connect to Git). Quando o
repositório não tem configuração do Wrangler, o Workers Builds **gera um
pull request automaticamente** com o `wrangler.jsonc` necessário, em vez de
exigir que alguém escreva isso à mão — o PR fica disponível para revisão
antes de qualquer coisa ir para produção, com um deploy de preview para
testar. Essa é a mesma lógica de "deixar a ferramenta fazer o trabalho
mecânico, revisar antes de aceitar" que já guia as migrações do backend
neste projeto (Alembic) — não escrever configuração de build à mão quando a
plataforma já sabe gerar a correta.

## Por que não o `@cloudflare/vite-plugin` (a forma "mais nativa" do TanStack Start)

A documentação do TanStack Start recomenda, como caminho principal para
Cloudflare, o pacote `@cloudflare/vite-plugin` registrado explicitamente no
`vite.config.ts`, com `wrangler.jsonc` escrito manualmente. Rejeitado aqui
pelo mesmo motivo que descartou a opção Netlify: exigiria editar o
`vite.config.ts` gerenciado pela Lovable, dentro do mesmo arquivo que já
avisa para não adicionar plugins manualmente. Como o Nitro (já configurado)
e o `@cloudflare/vite-plugin` (não configurado) resolvem o mesmo problema
por caminhos diferentes, usar os dois juntos seria redundante na melhor
hipótese e conflitante na pior. Ficar no que a Lovable já decidiu por
padrão é a opção que não mexe em nada que ela gerencia.

## Consequências

- Nenhuma mudança em `vite.config.ts` ou em qualquer arquivo do projeto
  antes de conectar o repositório ao Cloudflare — a conexão em si é feita
  pelo painel do Cloudflare (conta da Kamilly), não por um commit.
- O PR que o Workers Builds gerar (`wrangler.jsonc` novo) precisa ser lido
  e mesclado por alguém — na prática, a conversa do Claude Code do front,
  do mesmo jeito que revisa qualquer outro PR deste projeto.
- A URL final fica em `https://<algum-nome>.<subdomínio-da-conta>.workers.dev`
  por padrão, com a opção de anexar um domínio próprio depois pelo painel do
  Worker — sem custo adicional para isso, diferente da Lovable. **Já
  confirmada:** `https://planejamento-financeiro-front.kamillyrosarosa1-816.workers.dev`
  (primeiro deploy concluído).
- **O `CORS_ORIGINS` do backend (Fly.io) precisa ser atualizado com essa
  URL** — é a mesma pendência já registrada na Fase 2 de
  `PLANO-BACKEND.md`, agora com o comando final pronto para rodar.
- Variáveis de ambiente de produção (`VITE_API_URL`, ver ADR-03) são
  configuradas no painel do Worker (Settings → Variables and Secrets), não
  num arquivo `.env` commitado.

## Alternativas consideradas

- **Netlify com plugin oficial** e **`@cloudflare/vite-plugin` manual** —
  rejeitadas pelo mesmo motivo: as duas exigem editar um `vite.config.ts`
  que a Lovable já gerencia e avisa para não mexer, criando risco de
  conflito a cada sincronização futura da Lovable.
- **Hospedagem própria da Lovable** — rejeitada não por não funcionar, mas
  por exigir plano pago para domínio próprio e oferecer menos controle de
  infraestrutura sem ganho real de simplicidade em relação ao Cloudflare
  (que também é, na prática, "conectar e pronto").
