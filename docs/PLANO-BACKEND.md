# Plano de implementação — Backend (`planejamento-financeiro-back`)

Leia antes de codificar: `docs/specs/especificacao-tecnica-funcional.md`
(o que cada tela do frontend precisa) e `docs/adr/ADR-01-*.md`/`ADR-03-*.md`
(as duas decisões que afetam este repositório).

**Ponto de partida importante:** a API já existe e já funciona — este não é
um plano de "criar a API do zero". É um plano de ajuste para ela ficar
pronta para ser consumida por um segundo frontend, desacoplado, que ainda
não existia quando ela foi construída. Por isso as fases são pequenas: não
há nenhum endpoint novo a criar (confirmado na Parte 1 — todo dado que o
frontend Lovable precisa já tem endpoint), só padronização, CORS e
confirmação de contrato.

## Fase 1 — Tratamento global de erros (ADR-01)

**O quê:** adicionar em `app/main.py` os dois exception handlers descritos
no ADR-01 (`RequestValidationError` → `{"detail": ..., "campos": [...]}`;
`Exception` genérico → `{"detail": "Erro interno..."}`, `500`, com log).

**Por que primeiro:** é a mudança que todo o resto depende de estar
correta antes de o frontend começar a escrever tratamento de erro em cima
— se a Fase 1 mudar de formato depois que o frontend já integrou, o
retrabalho é do lado errado (mais telas para corrigir do que uma função
central no backend).

**Critério de aceite:** uma requisição que hoje devolve `422` em formato de
lista (ex.: `POST /anos/{ano}/lancamentos` com `valor` ausente) passa a
devolver `{"detail": "mensagem legível", "campos": [...]}`. Uma exceção não
tratada (simular, por exemplo, um erro de banco) devolve `500` com
`{"detail": "Erro interno..."}`, nunca um traceback cru.

**Testes existentes a ajustar:** `backend/tests/test_api.py` e
`backend/tests/test_auth.py` — qualquer asserção sobre o corpo de um `422`
precisa ser atualizada para o novo formato. Rodar `python -m pytest` depois
da mudança e corrigir os que quebrarem, não só os óbvios.

## Fase 2 — CORS para o novo frontend

**O quê:** confirmar a porta de desenvolvimento real do
`planejamento-financeiro-front` (`npm run dev` nesse repositório, verificar
a porta impressa no terminal — não assumir 5173, ver ADR-03) e adicionar ao
`.env` local e ao `CORS_ORIGINS` de produção (Fly.io:
`flyctl secrets set CORS_ORIGINS="http://localhost:5173,https://<url-do-front>"`,
mantendo as origens que já existiam se o frontend antigo continuar em uso).

**Por que depois da Fase 1:** não depende dela, mas é mais rápido de
verificar já com o frontend rodando localmente — faz sentido sequenciar
depois que alguém já rodou o outro repositório pela primeira vez.

**Critério de aceite:** uma requisição `fetch`/Axios feita a partir do
frontend rodando em `npm run dev` não é bloqueada por CORS no console do
navegador.

## Fase 3 — Confirmação de contrato (sem mudança de código, só validação)

**O quê:** conferir, endpoint por endpoint, que a Parte 1 deste pacote bate
com o comportamento real do backend em execução — não um exercício de
achar bug, mas uma rede de segurança antes do frontend começar a integrar
em cima de uma suposição errada. Especificamente:

- `GET /anos/{ano}/resumo` devolve os 12 meses mesmo para um ano recém-criado
  sem lançamento nenhum (valores zerados, não uma lista vazia)?
- `GET /anos/{ano}/lancamentos?mes=X` filtra corretamente — testar com um
  ano que já tenha dado real.
- `GET /categorias` sem `incluir_inativas` de fato omite as desativadas.
- `GET /contas` devolve o campo `tipo` preenchido para permitir ao
  frontend distinguir conta corrente de cartão no `<select>` da Fase 2 do
  plano de frontend.
- **Atualizado após a Etapa A do front** (Contas, Gastos Fixos, Fatura e
  Wishlist já existem em código mocado, ver Parte 1 seções 8–11): conferir
  também `POST .../{gasto_id}/meses/{mes}/pagar` e `.../desfazer` em
  `/anos/{ano}/gastos-fixos` (idempotência: chamar `pagar` duas vezes não
  duplica o lançamento), `GET /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}`
  e seus dois `POST` de pagar/desfazer, e `GET /anos/{ano}/wishlist/total`
  (os três campos `total_marcado`/`total_geral`/`quantidade_marcada` batem
  com o que a Parte 1 documenta).

**Critério de aceite:** uma chamada real a cada um dos 6 endpoints listados
no resumo da Parte 1 (`docs/specs/especificacao-tecnica-funcional.md`),
feita via `/docs` (Swagger) ou `curl`, com resposta conferida contra o TS
interface documentado ali. Qualquer divergência encontrada aqui volta para
a Parte 1 como uma correção do documento, antes do frontend integrar — mais
barato corrigir a spec agora do que depois de um hook já escrito em cima
dela.

### Resultado da execução — nenhuma divergência

Conferido contra a API em execução, com os dados reais de 2026. Cada
interface da Parte 1 foi comparada campo a campo com a resposta de verdade:

| Verificação | Resultado |
| --- | --- |
| `TokenOut`, `UsuarioOut` | conferem |
| `ContaOut` — inclusive `tipo` preenchido em todas as contas | confere |
| `CategoriaOut` — inativas omitidas sem `incluir_inativas` | confere (4 ativas de 6) |
| `ResumoAnoOut`, `ResumoMesOut`, `CarteirasContaOut` | conferem |
| 12 meses em ano recém-criado e vazio | confere |
| `LancamentoOut` e filtro `?mes=` | confere (231 lançamentos de 2026; nenhum vazou do filtro) |
| Valores monetários como string, nunca `number` | confere |
| Formato de erro do ADR-01 | confere (`detail` string + `campos`) |

A spec **não precisou de correção**. O roteiro usado para conferir não foi
versionado de propósito: ele depende de um usuário e de um ano de teste
criados e removidos na hora, e repetir a checagem é mais honesto refazendo-a
contra o estado real do que rodando um script que envelhece junto com a API.

### Segunda rodada — endpoints que a Etapa A do front passou a usar

Conferido num ano descartável (2098), criado e removido junto com as contas,
os lançamentos e a wishlist de teste — os dados reais de 2026 não foram
tocados.

| Verificação | Resultado |
| --- | --- |
| `GastoFixoOut` | confere |
| `gastos-fixos/.../pagar` duas vezes | mesmo lançamento, um só no mês |
| `gastos-fixos/.../desfazer` | `204`, lançamento removido, volta a `pendente` |
| `FaturaOut` — inclusive `dia_vencimento` | confere |
| Valor em aberto após compra no crédito | confere (`80.00`) |
| `fatura/.../pagar` duas vezes | mesmo lançamento, tipo `transferencia` |
| `fatura/.../desfazer` | `204`, volta a `pendente` com o valor de volta em aberto |
| `TotalWishlist` | confere (`300.00` de `4300.00`, 1 item) |

Duas correções de documento saíram daqui, as duas em favor do que o código
realmente faz:

- **A rota da fatura é `/fatura/{mes}`, não `?mes=`.** A versão da spec que
  veio na Etapa A tinha reintroduzido a forma com query param; confirmado que
  ela responde `404`. Corrigido na spec (o `CONTRATO-API.md` já estava certo).
- **`pagar` responde `201` também na segunda chamada**, não `200` como o
  contrato afirmava. O que importa — não duplicar o lançamento — está certo.
  Corrigido no `CONTRATO-API.md`.

## Fora desta rodada (decisões já registradas nas Partes 1 e 2, não tarefas)

- Nenhum endpoint de perfil de usuário (nome, meta de poupança, alertas) —
  ver seção 6 da Parte 1. Só entra como tarefa se/quando virar uma decisão
  de produto explícita, com ADR próprio.
- Nenhum endpoint de orçamento/meta por categoria — já decidido fora de
  escopo pelo ADR-0007 deste mesmo repositório, ver seção 7 da Parte 1.
- Nenhuma mudança em `CORSMiddleware` além da lista de origens (Fase 2) —
  `allow_credentials=True` fica como está, ver nota no ADR-03.
