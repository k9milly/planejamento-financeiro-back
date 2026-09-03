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
`.env` local e ao `CORS_ORIGINS` de produção (Fly.io):

> ⚠️ **Não rode o comando com a lista escrita à mão.** `flyctl secrets set`
> **substitui** o valor inteiro, não acrescenta. A versão anterior deste
> plano trazia a linha abaixo, que teria tirado o frontend antigo (Netlify)
> do ar em silêncio — ele estava publicado e não aparece nessa lista:
>
> ```
> flyctl secrets set CORS_ORIGINS="http://localhost:5173,https://...workers.dev"   # apaga o resto
> ```
>
> Como `flyctl secrets list` mostra só o digest, o valor atual precisa ser
> lido antes e a origem nova **somada** a ele:
>
> ```
> flyctl ssh console -C "printenv CORS_ORIGINS" --app planejamento-financeiro
> flyctl secrets set CORS_ORIGINS="<valor-atual>,<origem-nova>"
> ```
>
> Sem colchetes e sem aspas internas — o formato JSON já derrubou a produção
> em crash-loop uma vez (ver `app/config.py`). Definir um segredo **reinicia
> a aplicação**.

**Feito em 27/08/2026.** Dev local: porta **8080**, fixada pelo plugin da
Lovable (conferida rodando `npm run dev`, não assumida), no padrão de
`app/config.py` e travada por teste em `tests/test_config.py`. Produção:
`CORS_ORIGINS` passou a listar o Netlify **e** a URL do Cloudflare
(`https://planejamento-financeiro-front.kamillyrosarosa1-816.workers.dev`),
somando em vez de substituir. Verificado nas duas origens, e uma origem
desconhecida continua bloqueada.

Se um domínio customizado for anexado depois pelo painel do Worker, o
comando roda de novo somando a nova URL (a `workers.dev` não precisa sair).

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
  Wishlist já existem em código mocado, ver Parte 1 seções 8–10): conferir
  também `POST .../{gasto_id}/meses/{mes}/pagar` e `.../desfazer` em
  `/anos/{ano}/gastos-fixos` (idempotência: chamar `pagar` duas vezes não
  duplica o lançamento — testar manualmente), `GET
  /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}` (`{mes}` no caminho, não
  query string) e seus dois `POST` de pagar/desfazer, e `GET
  /anos/{ano}/wishlist/total` (os três campos
  `total_marcado`/`total_geral`/`quantidade_marcada` batem com o que a
  Parte 1 documenta).

  **Já verificado** pela própria conversa do backend, numa segunda rodada
  (branch `spec-etapa-a-e-validacao-extra`, ano descartável 2098, dados de
  2026 intocados): todos os itens acima conferem. Duas correções de
  documento saíram daí — a rota da fatura usa `{mes}` no caminho (a spec
  desta rodada tinha reintroduzido `?mes=`, que responde `404`), e `pagar`
  responde `201` também na segunda chamada, não `200`. As duas já foram
  aplicadas na Parte 1 e no `CONTRATO-API.md`. Essa branch está pronta para
  merge — só mexe em documentação, nenhuma mudança de código.

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

## Fase 4 — Perfil, meta de poupança e alertas de vencimento (ADR-06)

**O quê:** implementar o contrato da seção 12 da Parte 1
(`especificacao-tecnica-funcional.md`) — ler o `ADR-06` antes de codificar,
ele tem o raciocínio completo por trás de cada formato escolhido.

- Migração: `Usuario.nome` (string, opcional), `Usuario.alertas_email_ativo`
  (boolean, default `false`), tabela `MetaPoupanca` (`id`, `tipo` — enum
  `mensal`/`prazo`, `valor_alvo`, `data_alvo` nullable, `criada_em`,
  `ativa`).
- `GET /auth/eu` passa a incluir `nome`; `PATCH /auth/eu` novo, aceitando
  `nome` e `alertas_email_ativo` (o campo existe desde já, mesmo antes da
  Fase 5 abaixo — só não tem efeito observável até lá).
- `POST /metas-poupanca` cria e ativa (desativando automaticamente a meta
  anterior do mesmo `tipo`, se houver). `GET /metas-poupanca/ativas` devolve
  a meta mensal ativa e a meta com prazo ativa (cada uma pode ser `null`),
  cada uma já com o progresso calculado (`guardado_no_mes` ou
  `guardado_acumulado`, mais `percentual`) — reaproveitar a mesma lógica de
  agregação de lançamentos `guardado` que `GET /anos/{ano}/resumo` já usa,
  para não duplicar a regra em dois lugares.
- `GET /alertas` — consulta computada (sem tabela própria) sobre
  `GastoFixo`/`Conta` (cartões), devolvendo os itens não pagos com
  vencimento dentro de 3 dias (constante fixa nesta versão).

**Por que separado da Fase 5:** este bloco não depende de nenhuma
infraestrutura nova (é migração + endpoints normais, como o resto da API);
a Fase 5 (envio de e-mail) depende de escolher e configurar um serviço
externo, então não faz sentido travar a Fase 4 nisso.

**Critério de aceite:** os 168+ testes existentes continuam passando, mais
testes novos cobrindo: criar meta mensal desativa a mensal anterior mas não
mexe numa meta com prazo ativa (e vice-versa); `GET /metas-poupanca/ativas`
com nenhuma meta criada devolve `{mensal: null, prazo: null}`, não erro;
`GET /alertas` não devolve item já pago no mês, nem item com vencimento
fora da janela de 3 dias.

### Resultado da execução — feito, com duas correções de rumo

**195 testes passando** (168 antes desta fase + 27 novos). Migração
`e8b3c5d7f2a1` aplicada localmente com backup; **ainda não rodou em
produção**.

Duas coisas saíram diferentes do que a primeira implementação fez, e valem
registro porque as duas eram erros silenciosos — passariam nos testes e só
apareceriam em uso:

- **O progresso da meta com prazo conta só o que foi guardado depois de ela
  existir.** A primeira versão usou o saldo acumulado da reserva, que inclui
  tudo o que já havia antes: com R$ 13.041 guardados, uma meta de R$ 6.000
  criada hoje nasceria com "217% concluído". A regra de quais tipos mexem na
  reserva virou `services/calculos.py::variacao_do_guardado`, para não
  divergir da usada no cálculo mensal. A meta **mensal** continua olhando o
  guardado do mês corrente — ali o acumulado do mês é justamente o que se
  quer medir.
- **`GET /alertas` devolve o valor em aberto da fatura**, e não `null`. Uma
  fatura zerada deixa de virar alerta: não há o que pagar, e
  `.../fatura/{mes}/pagar` recusaria a operação — avisar ali ofereceria uma
  ação impossível. O valor sai de uma passada só do cálculo do ano, e não de
  `faturas._valor_em_aberto` por cartão, que refaria a conta inteira a cada
  chamada.

`Usuario.alertas_email_ativo` existe e é editável, mas **não tem efeito**
até a Fase 5 — está documentado no contrato para o front não expor o toggle
antes disso.

## Fase 5 — Alertas por e-mail (opcional, depois da Fase 4)

**O quê:** dar efeito real ao campo `Usuario.alertas_email_ativo` — quando
`true`, mandar um e-mail para os itens que `GET /alertas` retornaria.
Precisa de duas peças que não existem hoje no projeto:

- Um serviço de envio de e-mail (transacional, tipo Resend/SendGrid/SES, ou
  SMTP próprio — decisão em aberto, a tomar no início desta fase,
  registrando o porquê num ADR curto se a escolha não for óbvia).
- Algum mecanismo que rode periodicamente (ex.: uma vez por dia) e verifique
  vencimentos pendentes para quem tem a preferência ativa — pode ser um
  scheduler em processo (ex. APScheduler, já que o backend roda como um
  processo Python de qualquer forma) ou algo externo disparando um endpoint
  protegido; a escolha depende de como o deploy no Fly.io está configurado
  hoje (quantas instâncias, se reinicia com frequência), o que só o backend
  tem visibilidade pra decidir.

**Por que só depois da Fase 4:** o toggle e o campo já existem desde a Fase
4 — esta fase só liga o que ele faz. Isso permite que a Fase 4 seja
entregue e usada (nome, meta, alertas no app) sem ficar bloqueada esperando
uma decisão de infraestrutura de e-mail.

**Critério de aceite:** o front só deve expor o toggle de e-mail na
interface depois que esta fase estiver em produção — combinar esse timing
com a conversa do front antes de anunciar a Fase 4 como "pronta" para eles
integrarem o toggle.

## Fase 6 — Importação de extrato: generalizar para CSV e XLSX (ADR-08)

**Feito em 30/08/2026.** Registro do que foi implementado abaixo.

**O quê:** o subsistema de importação de extrato já existia e funcionava —
prévia + confirmação, deduplicação por `fitid`, sugestão de categoria via
`/regras` — mas só lia OFX. O `ADR-08` explica por que a decisão foi
generalizar em vez de recriar do zero.

- Dois parsers novos, `ler_csv` e `ler_xlsx`, em `app/services/tabular.py`,
  espelhando a assinatura de `ler_ofx` (bytes → lista normalizada). Layout
  aceito: colunas `data`/`valor`/`descricao` por nome de cabeçalho,
  ignorando acentos e maiúsculas, ordem livre — ver seção 13 da Parte 1.
- O tipo normalizado saiu de dentro do leitor de OFX: `TransacaoOFX` virou
  `TransacaoExtrato`, em `app/services/extrato.py`, junto com o erro base
  `ErroExtrato` e o cálculo do identificador sintético. Do roteador para
  dentro, nada sabe de qual formato a transação veio.
- `POST /anos/{ano}/importacao/ofx/previa` e `.../ofx/confirmar` viraram
  `POST /anos/{ano}/importacao/previa` e `.../confirmar`, com `formato`
  (`csv`/`xlsx`/`ofx`) obrigatório no multipart da prévia. Os schemas de
  resposta não mudaram. O rename foi seguro: uma busca no repositório do
  front confirmou zero ocorrências de `importacao`/`ofx` no código dele.
- Nenhuma migração e nenhuma dependência nova — `Lancamento.fitid` e
  `RegraCategorizacao` já sustentavam os três formatos, e o `openpyxl` já
  estava no `requirements.txt` por causa dos scripts da planilha antiga.

**Critério de aceite — atendido:** importar o mesmo extrato CSV ou XLSX duas
vezes não duplica lançamento (`test_reimportar_o_mesmo_extrato_nao_duplica`
parametrizado nos dois formatos novos); uma transação com mesma data/valor de
uma existente, mas descrição diferente, vem `possivel_repetido`, não
`duplicado`. A suíte inteira passa: 244 testes, 37 deles novos.

**Um teste a mais do que o critério pedia:** o mesmo extrato baixado em CSV e
em XLSX também não duplica. Como os dois usam o identificador sintético e ele
não depende do formato, isso já era verdade — o teste existe para que continue
sendo, já que baixar o extrato nos dois formatos é um engano fácil de cometer.

**Pendência conhecida:** o layout de colunas nunca foi conferido contra um
arquivo CSV/XLSX real do banco da Kamilly. Se divergir, o ajuste é mapear
nomes de coluna dentro de `tabular.py` — nada fora dele sabe como o arquivo é
feito, e nem o contrato nem a tela mudam.

## Fase 7 — Investimentos: caixinhas por conta (ADR-10)

**O quê:** implementar o contrato da seção 15 da Parte 1 — ler o
`ADR-10` antes de codificar, ele explica o porquê de cada decisão
(vínculo opcional com meta, escopo por conta, transferência direta).

- Migração: tabela `caixinhas` (`id`, `conta_id`, `nome`, `meta_id`
  nullable, `saldo`, `criada_em`, `ativa`). `Lancamento` ganha
  `caixinha_id` e `caixinha_destino_id` (ambos nullable).
  `TipoLancamento` ganha o valor `transferencia_caixinha`.
- `POST /contas/{conta_id}/caixinhas` aceita `saldo_inicial` opcional —
  validar que não passa do "guardado sem caixinha" da conta (guardado
  total da conta menos soma das caixinhas ativas já existentes) antes de
  aceitar.
- `caixinha_id` em `LancamentoCriar` aceito só quando `tipo` é
  `guardado`/`retirado`, ou `rendimento`/`perda` com
  `destino="guardado"` — e só se a caixinha pertencer à mesma
  `conta_id` do lançamento.
- `POST /contas/{conta_id}/caixinhas/transferir` cria um `Lancamento`
  `tipo=transferencia_caixinha` — não conta como entrada/saída do
  período nos agregados de `GET /anos/{ano}/resumo`, e não muda o total
  de `guardado` da conta (só realoca entre duas caixinhas dela). Exigir
  que origem e destino pertençam à mesma conta.
- `GET /metas-poupanca/ativas`: quando existir `Caixinha` com
  `meta_id` apontando pra uma meta ativa, trocar a fonte de
  `guardado_acumulado` (soma do `saldo` das caixinhas vinculadas) e de
  `guardado_no_mes` (soma dos lançamentos de guardado direcionados a
  essas caixinhas dentro do mês corrente) — sem mudar o schema da
  resposta. Sem caixinha vinculada, comportamento idêntico ao que o
  `ADR-06` já define.
- Desativar uma caixinha (`DELETE`) com saldo > 0 devolve esse saldo
  para "guardado sem caixinha" da conta — não é permitido apagar
  dinheiro, só soltar o rótulo.

**Critério de aceite:** criar duas caixinhas na mesma conta com
`saldo_inicial` que juntas excedem o guardado atual da conta é
rejeitado (`422`); transferir entre duas caixinhas da mesma conta não
altera `GET /anos/{ano}/resumo` (nem entradas/saídas, nem o guardado
total da conta); uma meta com caixinha vinculada reflete o saldo dela em
`guardado_acumulado`; os testes existentes de `GET
/metas-poupanca/ativas` sem caixinha vinculada continuam passando sem
alteração.

**Feito em 31/08/2026.** Duas coisas saíram diferentes do que o ADR-10
descreve, e valem revisão:

- **Não existe coluna `saldo` na caixinha.** O ADR a lista como campo; ela é
  derivada de `saldo_inicial` mais os lançamentos que apontam para a caixinha,
  como o progresso de `MetaPoupanca` já era. Uma coluna precisaria ser
  corrigida a cada criação, edição e exclusão de lançamento, e a primeira que
  escapasse deixaria o número mentindo em silêncio. De quebra, a desativação
  passou a funcionar sozinha: fora da lista de ativas, o dinheiro volta a
  contar como "sem caixinha", sem acerto de contas. **O contrato não muda** —
  `CaixinhaOut.saldo` continua saindo na resposta.
- **Caixinha só em conta corrente.** Um cartão de crédito não tem reserva
  (ADR-0002), então uma caixinha ali nunca poderia ter dinheiro. `422` com
  mensagem explicando.

**Uma armadilha que quase foi para produção:** `lancamentos.tipo` é um VARCHAR
dimensionado pelo nome mais longo do enum, e estava em `VARCHAR(13)`
(`TRANSFERENCIA`). `TRANSFERENCIA_CAIXINHA` tem 22 caracteres. O SQLite ignora
o tamanho declarado e a suíte inteira passava; o Postgres recusaria com *value
too long*, e a primeira transferência quebraria só lá — o mesmo formato do
incidente do default booleano. A migração agora alarga a coluna, e
`tests/test_schema_postgres.py` ganhou um teste que sobe um banco pelas
migrações e o compara com os modelos, para essa classe de divergência não
depender de alguém lembrar.

**Fora do que foi pedido, e não feito:** nada impede um `retirado` de deixar a
caixinha com saldo negativo. O ADR pede validação de saldo só na transferência
e no `saldo_inicial`, e é isso que existe. Cobrir o `retirado` exigiria
revalidar a caixinha inteira a cada edição e exclusão de lançamento — decisão
a tomar se acontecer na prática.

## Fora desta rodada (decisões já registradas nas Partes 1 e 2, não tarefas)

- Nenhum endpoint de orçamento/meta por categoria (`budgets`, dentro da tela
  `/metas`) — já decidido fora de escopo pelo ADR-0007 deste mesmo
  repositório, ver seção 7 da Parte 1. Diferente de meta de poupança
  (`goals`), que passou a ser real na Fase 4 acima.
- Alertas de progresso de meta de poupança ou de saldo baixo — fora de
  escopo por enquanto (ADR-06); só entram se virarem uma decisão de produto
  explícita depois.
- Nenhuma mudança em `CORSMiddleware` além da lista de origens (Fase 2) —
  `allow_credentials=True` fica como está, ver nota no ADR-03.
