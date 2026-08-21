# ADR-0001 — Forma de pagamento como campo do lançamento

**Status:** implementado

## Contexto

O sistema hoje não distingue *como* um gasto foi pago — só que saiu de uma
conta. Na prática, "paguei R$50 no débito" e "paguei R$50 no crédito" têm o
mesmo efeito contábil no modelo atual (`saldo -= valor`), mas têm efeitos
muito diferentes no dinheiro disponível de verdade: o débito sai agora, o
crédito só sai no vencimento da fatura.

`GastoFixo` já tem um campo `forma_pagamento`, mas é texto livre
(`String(60)`, default `""`) — serve só de anotação, não é usado em nenhuma
regra. Não existe o campo em `Lancamento`.

## Decisão

Criar o enum `FormaPagamento` com quatro valores fixos — `credito`, `debito`,
`pix`, `dinheiro` — e adicionar a coluna `forma_pagamento` (nullable) em
`Lancamento`.

Regras de coerência (mesma função `validar_coerencia` que já existe em
`schemas.py`, estendida):

- `forma_pagamento` só é aceito em lançamentos do tipo `saida` — mesma
  restrição que já existe para `categoria_id`. Guardar, retirar, transferir
  ou receber dinheiro não têm "forma de pagamento" no sentido em que o termo
  é usado aqui.
- O campo é **opcional**, não obrigatório. Um valor nulo é tratado como
  `debito` para efeitos de saldo — ou seja, o comportamento de hoje.

## Por que opcional, e não obrigatório

Tornar o campo obrigatório exigiria uma migração que decidisse a forma de
pagamento de cada lançamento histórico já existente — um dado que a
migração não tem como adivinhar corretamente. O projeto já tem um princípio
declarado para esse tipo de situação (ver `docs/REGRAS.md`, seção
"Tratamento de dados incompletos"): um dado incompleto não deve fazer
dinheiro desaparecer do saldo, nem forçar um palpite.

Tratando nulo como `debito`, a migração é puramente aditiva — nenhum
lançamento existente muda de comportamento — e o usuário passa a informar a
forma de pagamento só dali para frente, no seu próprio ritmo. A tela de novo
lançamento pode (e deve) vir com "débito" pré-selecionado para incentivar o
preenchimento, sem que isso seja imposto pelo banco.

## Consequências

- `validar_coerencia` ganha um parâmetro a mais e passa a receber não só o
  `conta_id`, mas também o **tipo** da conta (ver ADR-0002) para poder
  recusar, por exemplo, `forma_pagamento=credito` numa conta que não é
  cartão. Isso muda a assinatura da função e todos os três lugares que a
  chamam (`lancamentos.py`, `importacao.py`, o `model_validator` do
  `LancamentoCriar`).
- `GastoFixo.forma_pagamento` (texto livre) é renomeado para
  `forma_pagamento_legado` e passa a ser só histórico; um novo campo
  `forma_pagamento` (o mesmo enum) e `conta_id` (que já existe) assumem o
  papel de verdade. Ver spec "Forma de pagamento" para o detalhe da
  migração desse campo.
- A importação de extrato (OFX) não sabe a forma de pagamento — o banco não
  informa isso no arquivo. As linhas importadas nascem com
  `forma_pagamento=null` (tratado como débito), e o usuário ajusta na tela
  de revisão se for o caso. Isso é coerente com o restante da tela de
  importação, que já pede confirmação humana para tipo e categoria.

## Alternativas consideradas

- **Campo obrigatório com valor padrão fixo no banco.** Rejeitado: um
  default de banco (`server_default='debito'`) esconderia lançamentos sem
  forma de pagamento real por trás de um valor que parece informado. É
  melhor que `null` signifique explicitamente "não informado" e o app
  decida como tratá-lo, do que fingir que sempre houve uma resposta.
- **Forma de pagamento livre (texto), como hoje em `GastoFixo`.** Rejeitado:
  texto livre não permite a regra que sustenta todo o resto ("crédito não
  desconta do saldo") — o sistema precisaria interpretar string para saber
  se algo é ou não crédito, o que é frágil (`"Crédito"`, `"credito"`,
  `"cartão"` significariam a mesma coisa?).
