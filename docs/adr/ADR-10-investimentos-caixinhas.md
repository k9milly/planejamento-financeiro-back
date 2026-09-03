# ADR-10 — Investimentos: caixinhas por conta, vinculáveis a metas

**Status:** aceito

## Contexto

A Kamilly guarda dinheiro de verdade em caixinhas nomeadas dentro de cada
banco (hoje, duas no Mercado Pago: uma reserva geral e uma específica para
juntar o valor da fatura) — o sistema hoje só sabe somar um total de
"guardado" por conta, sem nome, sem separação. Ela pediu uma seção
**"Investimentos"**, onde é possível criar caixinhas, e que o lançamento
de tipo `guardado` passe a perguntar **para qual caixinha** o dinheiro
está indo.

Três decisões de produto precisavam ser tomadas antes de desenhar o
modelo de dados, porque cada uma mudava a forma do resto:

1. **Caixinha e meta de poupança (`ADR-06`) são a mesma coisa, coisas
   totalmente separadas, ou uma pode se ligar à outra?** A Kamilly
   escolheu: **uma caixinha pode ter uma meta vinculada, opcionalmente**
   — os dois continuam sendo entidades distintas (a `MetaPoupanca` do
   `ADR-06` não muda de forma), mas uma caixinha pode apontar para uma
   meta ativa, e aí o saldo dessa caixinha passa a alimentar o progresso
   daquela meta.
2. **Caixinha pertence a uma conta específica, ou é solta?** Escolhido:
   **por conta** — bate com a realidade (as caixinhas dela são do
   Mercado Pago, especificamente), e o sistema já rastreia guardado por
   conta hoje.
3. **Dá para mover dinheiro direto entre duas caixinhas, ou só
   entra/sai de cada uma separadamente?** Escolhido: **transferência
   direta entre caixinhas**, com um lançamento próprio para isso.

## Decisão

### Entidade nova: `Caixinha`

```
Caixinha
  id
  conta_id       # obrigatória — a caixinha pertence a uma conta
  nome           # texto livre, ex.: "Fatura do cartão"
  meta_id        # opcional — aponta para uma MetaPoupanca ativa
  saldo          # Decimal — quanto está guardado nesta caixinha especificamente
  criada_em
  ativa          # desativação é soft-delete, mesmo padrão de MetaPoupanca
```

`saldo` de uma caixinha é sempre uma **fração** do total já guardado na
conta — não é dinheiro novo. A soma dos saldos das caixinhas ativas de
uma conta nunca pode passar do total de `guardado` daquela conta; a
diferença é "guardado ainda sem caixinha" (o que já existia antes deste
ADR, ou o que a pessoa ainda não organizou em caixinhas).

### Criar caixinha — inclusive já com saldo (para migrar o que já existe)

```
POST /contas/{conta_id}/caixinhas
{
  nome: string,
  meta_id?: number | null,
  saldo_inicial?: string   // Decimal, default "0.00"
}
```

`saldo_inicial` existe exatamente para o caso da Kamilly agora: ela já
tem dinheiro guardado (lançado como um ajuste de saldo geral, sem
caixinha) e quer separar isso em caixinhas nomeadas retroativamente, sem
precisar fingir um novo lançamento de "guardado" que duplicaria o total.
Validação: `saldo_inicial` não pode ser maior que o "guardado sem
caixinha" da conta no momento da criação (guardado total da conta menos
soma das caixinhas ativas já existentes) — senão a caixinha estaria
inventando dinheiro que a conta não tem guardado.

### Lançar "guardado" para uma caixinha específica

`LancamentoCriar` ganha um campo novo, `caixinha_id` (opcional):

```
interface LancamentoCriar {
  // ...campos que já existem...
  caixinha_id?: number | null;
}
```

Aceito quando `tipo=guardado` ou `tipo=retirado` (a caixinha de onde sai
o dinheiro), e também quando `tipo` é `rendimento`/`perda` com
`destino="guardado"` (mesma lógica — se o rendimento vai para a reserva,
pode ir direto para uma caixinha específica). Quando ausente nesses
casos, o comportamento é o de hoje: entra no total de guardado da conta,
sem caixinha específica ("guardado sem caixinha"). Quando presente, a
caixinha precisa pertencer à mesma `conta_id` do lançamento — senão
`422`.

### Transferência direta entre caixinhas

Um lançamento de tipo novo, `transferencia_caixinha`:

```
POST /contas/{conta_id}/caixinhas/transferir
{
  caixinha_origem_id: number,
  caixinha_destino_id: number,
  valor: string   // Decimal, > 0, não pode passar do saldo da origem
}
```

Cria um `Lancamento` com `tipo=transferencia_caixinha`,
`caixinha_id=caixinha_origem_id`, `caixinha_destino_id=caixinha_destino_id`
(campo novo, só usado por este tipo) — fica registrado no histórico de
lançamentos, igual a qualquer outra movimentação, mas **não conta como
entrada nem saída** do período (o dinheiro nunca saiu da conta, só trocou
de rótulo) e **não muda o total de guardado da conta** — só realoca entre
duas caixinhas dela. `caixinha_origem_id` e `caixinha_destino_id`
precisam pertencer à mesma conta (transferência entre caixinhas de
contas diferentes fica fora deste v1 — teria que passar por retirar,
transferir entre contas, e guardar de novo, do jeito que já funciona
hoje).

Regras de coerência novas em `validar_coerencia`: `caixinha_destino_id`
só é aceito com `tipo=transferencia_caixinha`, e nesse tipo tanto
`caixinha_id` (origem) quanto `caixinha_destino_id` são obrigatórios;
nenhum outro campo (`categoria_id`, `forma_pagamento`, `conta_destino_id`,
`destino`) é aceito junto.

### Caixinha vinculada a uma meta — como o progresso é calculado

`MetaPoupanca` (`ADR-06`) não muda de formato. O que muda é a origem do
número de progresso, quando pelo menos uma caixinha aponta pra aquela
meta (`caixinha.meta_id = meta.id`):

- **Meta com prazo** (`guardado_acumulado`): soma o `saldo` atual das
  caixinhas vinculadas — faz sentido, porque é uma meta de acumular até
  uma data, e o saldo da caixinha já É o acumulado.
- **Meta mensal** (`guardado_no_mes`): soma só os lançamentos
  `tipo=guardado` (e `rendimento`/`perda` com destino guardado) que
  apontam para essas caixinhas **dentro do mês corrente** — não o saldo
  total da caixinha, porque a meta mensal é sobre o que entrou *este
  mês*, não o acumulado histórico.

Quando nenhuma caixinha aponta para a meta, nada muda — continua
somando o guardado da conta/ano inteiro, exatamente como o `ADR-06` já
define.

### Tela "Investimentos"

Nova, junto de Dashboard/Lançamentos/etc. no menu — lista as caixinhas
agrupadas por conta, cada uma mostrando nome, saldo, e (se tiver meta
vinculada) uma barra de progresso da meta. Ações: criar caixinha,
editar nome/meta vinculada, desativar, transferir entre duas caixinhas.
Desativar uma caixinha com saldo > 0 devolve esse saldo para "guardado
sem caixinha" da conta (não apaga o dinheiro, só solta o rótulo).

O seletor de "Conta" para "guardado"/"retirado" no modal de novo
lançamento (já existente) ganha um segundo seletor, condicional: depois
de escolher a conta, se ela tiver caixinhas ativas, aparece "Caixinha
(opcional)" listando as caixinhas daquela conta.

## Adendo de implementação (31/08/2026) — saldo nunca negativo

O ADR pede validação de saldo na transferência e no `saldo_inicial`. Ao
implementar, três outros caminhos levavam a uma caixinha negativa, e todos
foram reproduzidos antes de fechar: `retirado` maior que o saldo; apagar o
`guardado` que financiou uma retirada anterior; e editar o valor (ou o tipo) de
um lançamento já gravado.

A causa comum é o saldo ser derivado: validar a operação que está sendo feita
cobre só o primeiro caso. A trava passou a olhar o **resultado**, com a mudança
já aplicada na sessão e antes do commit, e vale para todo caminho que mexe em
caixinha.

## Adendo de implementação (31/08/2026) — não existe dinheiro solto

Um segundo caso apareceu: a soma das caixinhas passava do guardado da conta
quando uma retirada **sem caixinha** levava dinheiro que estava rotulado.
Nenhuma caixinha ficava negativa; o total da conta é que ficava menor que a
soma delas.

Ao rever, a Kamilly corrigiu uma premissa deste ADR. O texto acima trata
"guardado sem caixinha" como um estado normal e permanente ("o que a pessoa
ainda não organizou"). Não é: **todo dinheiro guardado está numa caixinha ou
num investimento.** O sem-caixinha existe só como estado de passagem, para o
dinheiro lançado antes de as caixinhas existirem — exatamente o que
`saldo_inicial` serve para rotular.

Com isso, a regra ficou mais simples do que a validação condicional que se
cogitou: assim que a conta ganha a primeira caixinha ativa, todo lançamento que
mexe na reserva daquela conta precisa dizer em qual. Vale nas duas portas que
criam lançamento — o cadastro/edição e a confirmação da importação, que ganhou
`caixinha_id` em `TransacaoConfirmar`. Conta sem caixinha nenhuma continua como
sempre foi.

## Consequências

- Migração nova: tabela `caixinhas`; `Lancamento` ganha `caixinha_id` e
  `caixinha_destino_id` (ambos nullable); `TipoLancamento` ganha o valor
  `transferencia_caixinha`.
- Endpoints novos: `POST`/`GET`/`PATCH`/`DELETE
  /contas/{conta_id}/caixinhas`, `POST
  /contas/{conta_id}/caixinhas/transferir`.
- `GET /metas-poupanca/ativas` não muda de schema, só passa a computar
  `guardado_no_mes`/`guardado_acumulado` diferente quando há caixinha
  vinculada — o front não precisa mudar nada na leitura dessa resposta.
- Nenhum endpoint existente perde compatibilidade: `caixinha_id` é
  sempre opcional, então lançamentos antigos (e integrações que ainda
  não mandam esse campo) continuam funcionando exatamente como hoje.
- Para migrar o dinheiro já guardado (os R$ 13.438,45 que a Kamilly
  acabou de lançar como ajuste, sem caixinha) para as duas caixinhas
  reais, ela usa o `saldo_inicial` na criação de cada caixinha — não
  precisa lançar nada de novo.

## Alternativas consideradas

- **Caixinha substituir meta de poupança** (unificar os dois conceitos
  num só) — descartada; a Kamilly preferiu manter os dois conceitos
  separados, com um vínculo opcional entre eles, em vez de reescrever o
  que o `ADR-06` já define.
- **Caixinha sem vínculo com conta** — descartada; não bate com a
  realidade de como caixinha funciona nos bancos dela, e perderia o
  reaproveitamento do que o sistema já rastreia por conta.
- **Sem transferência direta entre caixinhas** (só retirar de uma e
  guardar em outra, em dois lançamentos) — era a opção mais simples,
  descartada porque a Kamilly especificamente pediu poder mover direto.
- **Transferência entre caixinhas de contas diferentes** — fora deste
  v1; nenhum caso de uso foi trazido para isso, e complicaria a validação
  de coerência sem necessidade agora.
