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

**Feito em 03/09/2026.** Duas coisas saíram diferentes do que o ADR-10
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

**Caixinha nunca fica negativa.** O ADR pede validação de saldo só na
transferência e no `saldo_inicial`; isso deixava três caminhos abertos, todos
verificados na prática antes de fechar:

| Caminho | O que dava |
| --- | --- |
| `retirado` maior que o saldo da caixinha | `-400,00` |
| apagar o `guardado` que financiou uma retirada anterior | `-500,00` |
| editar o valor de uma retirada já gravada | `-400,00` |

Checar a operação que a pessoa está fazendo cobriria só o primeiro. Como o
saldo é derivado, a trava (`garantir_nao_negativas`) olha o **resultado**: roda
com a mudança já aplicada na sessão, no `flush`, antes do `commit` — recusar
ali deixa a transação sem gravar. Vale para criar, editar, excluir e
transferir. Um `PATCH` confere também a caixinha de onde o lançamento saiu, não
só a de destino.

Lançamentos sem caixinha não mudaram de comportamento.

**Numa conta com caixinhas, todo dinheiro guardado está em uma delas.** A
Kamilly corrigiu a premissa: não existe "dinheiro solto" na reserva — ele está
numa caixinha ou num investimento. Então a exigência não é condicional a
sobrar ou não dinheiro sem rótulo; vale a partir da **primeira caixinha ativa**
da conta.

Sem ela, o total da conta e a soma das caixinhas desencontram sem que nenhuma
caixinha fique negativa. Com R$ 1.000 divididos em duas caixinhas, retirar
R$ 300 sem escolher deixava a conta com R$ 700 guardados e as caixinhas
somando R$ 1.000.

Aplicada nos tipos que mexem na reserva (`guardado`, `retirado`, e
`rendimento`/`perda` com `destino="guardado"`), nas **duas** portas que criam
lançamento: o cadastro/edição e a confirmação da importação — que por isso
ganhou `caixinha_id` em `TransacaoConfirmar`. `entrada`, `saida` e
transferência entre contas não são afetadas.

Uma conta sem caixinha nenhuma continua exatamente como antes: não há o que
escolher. É isso que permite lançar o guardado primeiro e organizar em
caixinhas depois, com `saldo_inicial` — o caminho da migração da Kamilly.

## Fase 8 — Orçamento por categoria: limite real (ADR-11)

**O quê:** reverte o `ADR-0007` deste repositório — ler o `ADR-11` antes
de codificar, ele explica o porquê (a Kamilly pediu depois de usar a
tela). Ver seção 16 da Parte 1 para o contrato completo.

- Migração pequena: `Categoria.limite_mensal` (Decimal, nullable) e
  `Usuario.mostrar_orcamento_categoria` (boolean, default `true`).
- `POST /categorias`, `PATCH /categorias/{id}` e `GET /categorias`
  passam a aceitar/devolver `limite_mensal` — endpoints já existem, só
  ganham um campo.
- `PATCH /auth/eu` (já existe, do ADR-06) ganha
  `mostrar_orcamento_categoria`.
- Nenhuma mudança na agregação de gasto por categoria — `ResumoMesOut.
  gastos_por_categoria` já existe e já está correta; o cálculo de %
  contra o limite é feito no frontend.

**Critério de aceite:** criar uma categoria com `limite_mensal="600.00"`,
depois editar para `null`, remove o limite sem apagar a categoria nem
seus lançamentos históricos. `mostrar_orcamento_categoria` tem default
`true` para usuários existentes (não precisa de migração de dados, só de
schema).

**Feito em 05/09/2026.** Saiu como o ADR-11 pede: dois campos, nenhum
endpoint novo, nenhuma mudança na agregação de gasto por categoria.

Duas decisões pequenas que o ADR não especificava:

- **`limite_mensal` precisa ser maior que zero** (`422` se for `0` ou
  negativo), com `CHECK` no banco também. Um teto de zero não quer dizer
  nada — quem não tem orçamento usa `null`, que é o padrão e continua sendo
  uma categoria de uso normal.
- **O `CHECK` trata `NULL` explicitamente** (`limite_mensal IS NULL OR
  limite_mensal > 0`). Em SQL `NULL > 0` é desconhecido, não falso, e uma
  restrição desconhecida passa — mas escrever a intenção evita que alguém
  "simplifique" depois achando que dá no mesmo em todo dialeto.

**O que fez a diferença entre ausente e nulo funcionar** já estava lá: o
`PATCH /categorias/{id}` usa `model_dump(exclude_unset=True)`. Sem isso,
editar só a cor apagaria o limite junto. Há teste cobrindo os dois casos, e
confirmei que ele falha se o `exclude_unset` sair.

**Um teste antigo precisou ser atualizado, e é bom que tenha precisado:**
`test_eu_traz_os_campos_novos` trava o conjunto exato de campos de
`GET /auth/eu`. Ele quebrou ao ganhar `mostrar_orcamento_categoria` —
exatamente o que ele existe para fazer, já que essa é a resposta que o
frontend lê na abertura. Atualizei o conjunto em vez de afrouxar a asserção.

**Nada a fazer sobre dados existentes:** `limite_mensal` nasce nulo e
`mostrar_orcamento_categoria` nasce `true` pelo `server_default`, inclusive
para as linhas que já estão no banco.

**Feito em 25/09/2026.** Saiu como o ADR-14 pede, com os três modos de
cálculo e o teto de 24 parcelas.

- **`valor_total` entra e sai com significados diferentes.** Na entrada do modo
  percentual é o preço à vista; na saída é sempre a soma efetiva das parcelas,
  com juros. Está assim no ADR (o comentário do modelo diz "soma efetiva") e
  foi implementado assim, mas é um nome só para dois números — registrado aqui
  porque é o tipo de coisa que confunde quem lê o contrato depois.
- **A primeira parcela precisa ser do ano da rota.** O ADR diz que `{ano}` é o
  ano da primeira parcela; sem checar, mandar uma data de outro ano gravaria a
  compra num ano e as parcelas em outro, sem erro nenhum.
- **Recusar ano arquivado não grava metade.** A checagem acontece antes de
  qualquer parcela ser criada, e sem `commit` — o teste confirma que nenhum
  lançamento sobra.

**Nenhuma mudança em `services/calculos.py`**, como o ADR previa. Há teste
verificando que a fatura do cartão em março fecha devendo a primeira parcela e
a de abril, as duas primeiras — sem nenhuma linha nova de cálculo.

## Fora desta rodada (decisões já registradas nas Partes 1 e 2, não tarefas)

- ~~Nenhum endpoint de orçamento/meta por categoria~~ — **revertido pelo
  ADR-11 na Fase 8 acima.** O limite por categoria virou
  `Categoria.limite_mensal`, real e editável. Meta de poupança (`goals`) já
  tinha virado real na Fase 4.
- Alertas de progresso de meta de poupança ou de saldo baixo — fora de
  escopo por enquanto (ADR-06); só entram se virarem uma decisão de produto
  explícita depois.
- Nenhuma mudança em `CORSMiddleware` além da lista de origens (Fase 2) —
  `allow_credentials=True` fica como está, ver nota no ADR-03.

---

## Fase 9 — Metas de poupança viram lista, vínculo com wishlist (ADR-13)

**O quê:** ler o `ADR-13` inteiro antes de codificar — reverte a parte do
ADR-06 que limitava a uma meta ativa por tipo. Contrato completo na seção
17 da spec (`docs/specs/especificacao-tecnica-funcional.md`).

- Migração: `metas_poupanca.nome` (`String(60)`, nullable) e
  `metas_poupanca.wishlist_item_id` (FK `wishlist.id`, `ON DELETE SET NULL`,
  nullable, indexado). Aditiva, nenhum dado existente muda de
  comportamento.
- `routers/metas_poupanca.py::criar()` para de aposentar metas do mesmo
  tipo — remover só esse trecho, o resto da função continua igual.
- `routers/metas_poupanca.py::ativas()` passa de `.first()` pra `.all()`
  na busca de metas ativas de cada tipo, e o `MetasAtivasOut` muda de
  `{mensal, prazo}` (nuláveis) pra `{mensais: [...], prazos: [...]}`
  (listas). `_progresso_mensal`/`_progresso_prazo`/`_caixinhas_da_meta`
  não mudam — continuam operando sobre uma `MetaPoupanca` por chamada, só
  passam a ser chamadas em loop.
- `MetaPoupancaCriar`/`MetaPoupancaAtualizar` (schemas.py) ganham
  `nome?: str` e `wishlist_item_id?: int`. Validar que o item existe
  quando informado (mesmo padrão de `_validar_conta` em outros routers) —
  `422` se não existir.

**Critério de aceite:** criar duas metas `prazo` seguidas não desativa a
primeira (comportamento antigo do ADR-06 não deve mais acontecer). Criar
uma meta com `wishlist_item_id` de um item que não existe devolve `422`.
Apagar um item da wishlist que tem meta vinculada não apaga a meta — só
zera `wishlist_item_id` dela (`SET NULL`).

**Testes a ajustar:** `test_perfil_metas_alertas.py` — os que hoje
verificam "criar meta do mesmo tipo aposenta a anterior" mudam de
expectativa (as duas continuam ativas). Testes novos: `wishlist_item_id`
(criar com vínculo válido, `422` com item inexistente, `SET NULL` ao
apagar o item), e `GET /metas-poupanca/ativas` devolvendo várias metas do
mesmo tipo.

**Feito em 25/09/2026.** Saiu como o ADR-13 pede. Três observações:

- **`_progresso_mensal` e `_progresso_prazo` deixaram de aceitar `None`.** O
  `| None` delas era a forma de dizer "não existe meta deste tipo", e isso
  virou lista vazia — manter o parâmetro opcional seria carregar um caso que
  não existe mais.
- **A ordem de cópia para o Postgres mudou.** `ItemWishlist` subiu para antes
  de `MetaPoupanca`, porque a meta passou a apontar para o desejo. O
  `test_copia.py` pegou isso sozinho, pela quarta vez desde que existe.
- **`MetaPoupancaAtualizar` não existe, e não foi criado** — ver a pendência
  no fim desta seção.

**Um achado que vale além desta fase:** o `SET NULL` do vínculo não funcionava
nos testes, e não por causa do ADR — **o SQLite ignora chave estrangeira se
ninguém pedir**. `PRAGMA foreign_keys` nasce desligado, então `SET NULL`,
`CASCADE` e `RESTRICT` nunca foram exercidos aqui, enquanto valem integralmente
no Postgres de produção. É a pior forma de divergência: a suíte passa e o
comportamento real é outro.

`app/database.py` agora liga o pragma em toda conexão SQLite, registrando no
`Engine` genérico — os testes criam a própria engine, e prendê-lo só na da
aplicação deixaria o buraco aberto justamente onde ele importa. Nenhum teste
existente quebrou com as chaves ligadas, o que é uma boa notícia: as regras já
estavam certas, só não eram verificadas.

**Pendência de contrato, não resolvida de propósito:** o ADR-13 cita
`MetaPoupancaAtualizar` nas Consequências, mas **não existe `PATCH
/metas-poupanca/{id}`** neste backend — nunca existiu, e a seção 17 da spec não
o descreve. Implementei só o que a spec descreve. Vale decidir: sem PATCH, o
`nome` e o `wishlist_item_id` só podem ser definidos na criação, e corrigir
qualquer um dos dois exige desativar a meta e criar outra — perdendo o
histórico. É a mesma armadilha que o `saldo_inicial` das caixinhas criou (ver
ADR-10), e que precisou ser desfeita depois.

## Fase 10 — Parcelamento no cartão de crédito (ADR-14)

**O quê:** ler o `ADR-14` inteiro antes de codificar, principalmente a
tabela dos três modos de cálculo de juros (sem juros / valor da parcela
digitado / taxa % calculada) — não são intercambiáveis, e a fórmula do
modo percentual (juros simples) está justificada lá, não reinventar outra.
Contrato completo na seção 18 da spec.

- Migração: tabela `compras_parceladas` nova (ver modelo completo no
  ADR-14) + `lancamentos.compra_parcelada_id` (FK, `ON DELETE CASCADE`,
  nullable, indexado) + `lancamentos.numero_parcela` (Integer, nullable).
- Endpoint novo `POST /anos/{ano}/compras-parceladas`: valida que
  `conta_id` é `cartao_credito` (reaproveitar a validação já usada em
  `lancamentos.py`/`gastos_fixos.py`), calcula `valor_parcela`/`valor_total`
  conforme o modo, cria os anos que faltarem para as parcelas futuras
  (mesmo formato de `POST /anos`, sem saldos iniciais — `422` se algum ano
  de destino já existir arquivado), e gera N `Lancamento` — um por mês, a
  partir de `data_primeira_parcela`, com o mesmo tratamento de "dia
  inexistente no mês" que `gastos_fixos.py::pagar()` já usa
  (`calendar.monthrange`).
- Endpoint novo `DELETE /anos/{ano}/compras-parceladas/{id}`: apaga o
  grupo; o `CASCADE` remove as parcelas que ainda existirem como
  lançamento, em qualquer ano.
- Nenhuma mudança em `services/calculos.py` — cada parcela é um
  `Lancamento` comum do ponto de vista do cálculo de saldo/fatura.

**Critério de aceite:** parcelar R$100 em 3x sem juros gera R$33,33 +
R$33,33 + R$33,34 (a diferença de arredondamento cai na última parcela).
Parcelar com juros por taxa % bate com a fórmula de juros simples do ADR;
parcelar com juros por valor de parcela não faz nenhum cálculo financeiro,
só multiplica. Parcelar 12x a partir de novembro/2026 cria o ano 2027
sozinho, se ainda não existir. Apagar o grupo remove as parcelas ainda
não editadas manualmente (idem: parcelas editadas continuam sendo
apagadas junto, `ON DELETE CASCADE` não distingue).

**Testes a criar:** os três modos de cálculo (incluindo arredondamento),
criação automática de ano faltante, `422` em ano de destino arquivado,
`422` em conta que não é cartão, `CASCADE` ao apagar o grupo, e que editar
uma parcela isolada via `PATCH /anos/{ano}/lancamentos/{id}` continua
funcionando sem regra nova.

---

## Fase 11 — Espaços financeiros compartilhados e isolamento de dados (ADR-15)

**Por que primeiro, antes de qualquer outra coisa desta leva:** as Fases
12 e 13 (cadastro aberto, convites, limite de tentativas) dependem de
"espaço" já existir como conceito — cadastro cria um espaço, convite
vincula a um. Ler o `ADR-15` inteiro antes de codificar; é a mudança mais
arriscada do projeto até aqui (acertar errado vaza dado financeiro de uma
família pra outra), então vale reler duas vezes antes de migrar.

**O quê:**

- Tabelas novas `espacos` e `membros_espaco` (modelo completo no ADR-15).
- Coluna `espaco_id` em **todas** as catorze tabelas de dado financeiro —
  sim, até as que já têm `ano_id` (o ADR explica por que não confiar só na
  cadeia transitiva via `Ano`).
- Migração de backfill: cria um espaço único, vincula o usuário existente
  como dono, preenche `espaco_id` de toda linha existente com esse id.
- `app/espaco.py` novo: o `contextvar` + os dois eventos do SQLAlchemy
  (`do_orm_execute` pro filtro automático de leitura, `before_flush` pro
  carimbo automático em linha nova) — é o coração do ADR, não uma
  escolha de implementação qualquer; ler a seção "Por que no nível da
  sessão, não em cada router" antes de propor outra abordagem.
- `deps.py::usuario_atual` passa a fixar o `contextvar` a partir de
  `usuario.espaco_atual_id`.
- Endpoints novos: `PATCH /auth/espaco-atual`, `GET`/`PATCH /espacos/{id}`,
  `GET`/`DELETE /espacos/{id}/membros/{usuario_id}`,
  `GET /espacos/{id}/exportar`, `DELETE /auth/eu` (os três casos do ADR:
  dono solo apaga tudo, dono com outros membros é bloqueado, membro só
  sai).
- `GET /auth/eu` ganha `espaco_atual_id` e `espacos: EspacoOut[]`.

**Critério de aceite — o que importa mais que qualquer outra coisa nesta
fase:** criar dois espaços, cada um com um "Ano 2026" e uma "Categoria
Alimentação" (ids diferentes, nomes iguais, de propósito), logar como
membro de cada um e confirmar que **nenhum** endpoint de leitura do
sistema deixa vazar uma linha de um espaço pro outro. Isso precisa ser um
teste automatizado cobrindo todo router, não uma checagem manual.

**Script administrativo:** `scripts/criar_usuario.py` roda fora de
contexto de requisição (sem `contextvar` fixado) — precisa criar o espaço
do usuário novo manualmente, replicando a mesma lógica do cadastro (Fase
12) nessa escala menor.

**Feito em 11/10/2026.** Saiu como o ADR-15 pede no resultado, e **diferente
em dois pontos do mecanismo** — os dois descobertos por teste, não por
leitura:

- **O espaço ativo mora na sessão do banco, não num `ContextVar`.** O ADR
  propunha `contextvars.ContextVar`, e isso não funciona com o FastAPI: ele
  roda dependência e endpoint síncronos em chamadas separadas de
  `anyio.to_thread.run_sync`, cada uma com uma **cópia** do contexto, então o
  `set()` feito em `usuario_atual` não chega ao endpoint. O sintoma era
  `NOT NULL constraint failed: contas.espaco_id` em todo `POST`. A `Session` é
  um objeto só, criado por requisição e entregue aos dois, então o espaço
  ficou em `db.info` — ver a explicação inteira em `app/espaco.py`.
- **Usuário autenticado sem espaço não pode cair no "sem filtro".** O ADR
  manda não filtrar quando não há espaço, o que está certo para script e
  teste e errado para quem está logado e ainda não escolheu: seria o único
  estado do sistema em que ver tudo é o padrão. Existe um sentinela
  (`SEM_ESPACO = -1`) que não casa com linha nenhuma. Falha fechado.

**Cinco restrições de unicidade globais, que o ADR não menciona, tornavam o
próprio critério de aceite dele impossível.** `anos.ano`, `contas.nome`,
`categorias.nome` e `regras_categorizacao.padrao` eram únicos no sistema
inteiro — dois espaços não conseguiriam ter "2026", "Nubank" ou "Alimentação"
cada um, que é literalmente o que o teste de aceite manda criar. Pior:
`cores_forma_pagamento` tinha a **forma de pagamento como chave primária**,
então o primeiro espaço a escolher uma cor de crédito impediria todos os
outros. As cinco viraram unicidade por espaço, e a última virou chave
composta.

**A lista de modelos protegidos não é escrita à mão.** O ADR trazia uma tupla
`MODELOS_COM_ESPACO`. Virou descoberta por herança (`modelos_protegidos()`
percorre quem herda do mixin `ComEspaco`), porque uma lista é algo que alguém
precisa lembrar de atualizar na décima quinta tabela — e esquecer significa
uma tabela sem isolamento, exatamente a falha silenciosa que o módulo existe
para fechar. A exportação usa a mesma descoberta, então tabela nova entra no
arquivo exportado sozinha.

**Um achado que vale além desta fase: a varredura de rotas não prova que o
filtro existe.** O teste de mutação desligou o filtro de leitura só para
`lancamentos` e **toda a varredura de endpoints continuou verde** — porque as
rotas de lançamento pedem `/anos/2026/...` e o lançamento alheio fica de fora
por pertencer ao `Ano` do outro espaço, não porque o filtro funcionou. É a
proteção transitiva que o ADR decidiu não confiar, dando cobertura a si mesma.
Quem pega a falha é `TestFiltroDaSessao`, que consulta as catorze tabelas
direto. **Lição para as próximas fases: teste por rota mede o sistema de hoje;
só teste no nível do mecanismo mede o mecanismo.**

**Um bug real encontrado pelo teste, em código que já estava em produção:**
`PUT /preferencias/cores-forma-pagamento/{forma}` usava
`db.get(CorFormaPagamento, forma)`, e com a chave primária composta isso
levanta `InvalidRequestError` — a rota responderia `500`. Virou consulta
filtrada.

**Conferido sobre `db.get`:** metade dos routers lê por chave primária, e
`db.get` é a única leitura que poderia atalhar o filtro (responde do mapa de
identidade sem ir ao banco). Confirmado em teste que ele **é** filtrado quando
a sessão tem espaço fixado antes da primeira leitura — que é o que
`usuario_atual` garante. O único lugar onde o espaço muda no meio da sessão é
`GET /espacos/{id}/exportar`, e lá só há `query().all()`, que sempre vai ao
banco.

**Corrigido em 13/10/2026, achado pelo frontend:** `DELETE /auth/eu`
respondia `500` sempre que o espaço tinha uma conta com lançamentos. `espaco_id`
é `CASCADE` em toda tabela, então apagar o espaço manda o banco apagar `contas`
— e `lancamentos.conta_id` é `RESTRICT`, de propósito, porque apagar conta com
lançamento é um engano que o sistema deve recusar. `gastos_fixos`, `caixinhas` e
`compras_parceladas` são iguais. As duas regras estão certas separadas e se
contradizem juntas; quem resolve é `apagar_espaco()`, que apaga filho antes de
pai usando a ordem topológica de `Base.metadata.sorted_tables`.

**E este é o segundo caso, na mesma fase, de suíte verde por sorte** — vale mais
que o defeito em si. O teste equivalente existia e passava, porque o SQLite
dispara os cascatas na ordem em que as chaves estrangeiras foram declaradas, e
`create_all` (que os testes usam) declara numa ordem em que funciona, enquanto a
migração declara em outra em que não. O primeiro caso foi a varredura de rotas
protegida pela cadeia transitiva do `Ano`. Os dois têm a mesma forma: **o teste
media o arranjo, não o mecanismo.**

O par de lições virou prática: há agora um teste que sobe o banco **pelas
migrações**, e não por `create_all`, para o caminho de exclusão —
`TestExclusaoEmBancoMigrado` — com o contrapeso que confirma que o cascata cru
realmente falha ali, para a proteção não virar enfeite.

**Conferido em produção:** no **Postgres o cascata cru funciona** — a ordem em
que ele resolve as ações de chave estrangeira é favorável. Então produção nunca
esteve quebrada por isso; só o SQLite, que é onde o frontend testa. Conferido
com um espaço descartável, dentro de uma transação desfeita, sem tocar em dado
real. Depois da correção a ordem é nossa nos dois dialetos, e deixa de depender
de sorte em qualquer um.

**Lacuna de contrato, registrada e não inventada:** a especificação diz que
remover membro é "só dono", então **não existe "sair do espaço"** por
iniciativa do membro. Está no `CONTRATO-API.md`.

**Divergência de contrato a resolver com ela:** a seção 20 declara
`espaco_atual_id: number`, e ele é `number | null` de verdade — fica nulo
quando a pessoa é removida do espaço que estava vendo. Importa porque, nesse
estado, toda listagem volta vazia: a tela precisa diferenciar "escolha um
espaço" de "não tem nada cadastrado".

**Migração:** `d7f3a0c21e58`. O espaço inicial é criado **sempre**, e não só
quando existe usuário — a primeira versão falhava com
`NOT NULL constraint failed: _alembic_tmp_contas.espaco_id` porque a migração
inicial do projeto semeia duas contas, então nem um banco recém-migrado está
vazio. `upgrade` e `downgrade` conferidos nos dois dialetos.

## Fase 12 — Cadastro aberto, convite para espaço e recuperação de senha (ADR-16)

**Depende da Fase 11 e da Fase 13 em produção ao mesmo tempo** — nenhuma
das duas sozinha é segura: cadastro aberto sem limite de tentativas é
convite a abuso.

**O quê:**

- Tabela `tokens_acao` (verificação de e-mail e redefinição de senha,
  reaproveitando a mesma estrutura — ver ADR-16) e `convites_espaco`.
- `usuarios.email_verificado` (boolean, default `false`).
- `POST /auth/cadastro`, `POST /auth/esqueci-senha`,
  `POST /auth/redefinir-senha`, `POST /auth/reenviar-verificacao`.
- `POST /espacos/{id}/convites`, `GET /convites/{token}`,
  `POST /convites/{token}/aceitar`.
- `app/services/email.py` novo — `enviar_email()` loga o link em vez de
  enviar de verdade, até a Kamilly configurar um provedor (Resend, SES,
  etc.). Ver a seção "O envio de e-mail de verdade é a única parte que
  fica pendente" no ADR — não é um TODO solto, é a forma pretendida de
  entregar isto por agora.

**Critério de aceite:** cadastro cria o `Usuario` + `Espaco` + `MembroEspaco`
numa transação só; cadastro com e-mail de convite pendente entra no
espaço convidado em vez de criar um novo (testar os dois caminhos);
recuperação de senha nunca revela se o e-mail existe; link de qualquer um
dos três fluxos aparece no log do servidor, legível, em desenvolvimento.

## Fase 13 — Limite de tentativas em login, cadastro e recuperação (ADR-17)

**O quê:** tabela `tentativas_acesso`, função `verificar_limite`/
`registrar_tentativa` chamada no início de `login`, `cadastro` e
`esqueci_senha`. Limite: 5 tentativas por e-mail normalizado **e** por IP
em 15 minutos, `429` quando excedido, nunca revelando qual dos dois
limites foi atingido.

**Critério de aceite:** 6ª tentativa errada de login no mesmo e-mail
dentro de 15 minutos responde `429`; esperar a janela passar libera de
novo; IPs/e-mails diferentes não se bloqueiam entre si.

**Importante:** sem esta fase em produção, não habilitar `/auth/cadastro`
nem `/auth/esqueci-senha` publicamente — mesmo que o código da Fase 12
esteja pronto, os dois endpoints públicos sem limite de tentativas são um
risco novo que hoje não existe (login sozinho, sem cadastro aberto, tinha
superfície de ataque menor).
