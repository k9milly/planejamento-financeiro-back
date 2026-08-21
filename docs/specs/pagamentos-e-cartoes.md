# Spec — Forma de pagamento, contas/cartões e saldo inteligente

Cobre as quatro mudanças pedidas. As decisões de arquitetura por trás de cada
uma estão nos ADRs 0001–0003, em `docs/adr/`; este documento é o "o quê",
aqueles são o "por quê".

Convenção: nomes de campo em `snake_case`, como o resto do backend. `Decimal`
para tudo que é dinheiro, serializado como string, como já é.

---

## 1. Forma de pagamento

### Modelo

`backend/app/models.py`

```python
class FormaPagamento(str, enum.Enum):
    CREDITO = "credito"
    DEBITO = "debito"
    PIX = "pix"
    DINHEIRO = "dinheiro"
```

`Lancamento` ganha:

```python
forma_pagamento: Mapped[FormaPagamento | None] = mapped_column(
    Enum(FormaPagamento, native_enum=False), nullable=True
)
```

`GastoFixo`:
- coluna atual `forma_pagamento: Mapped[str]` (texto livre) é renomeada para
  `forma_pagamento_legado`, mantida só para exibição do que já estava
  escrito lá (ex.: "boleto", "débito automático") — nenhuma regra nova lê
  esse campo.
- nova coluna `forma_pagamento: Mapped[FormaPagamento | None]`, mesmo enum.

### Regras de coerência (`validar_coerencia`, em `schemas.py`)

- `forma_pagamento` só é aceito quando `tipo == SAIDA`. Nos demais tipos,
  informar o campo é erro 422 — mesma regra que já existe para
  `categoria_id`.
- `forma_pagamento` é **opcional**. `None` é tratado como equivalente a
  `DEBITO` em todo lugar que olha o campo (cálculo de saldo, validação de
  conta compatível — ver seção 3).
- Quando `forma_pagamento == CREDITO`: `conta_id` **precisa** apontar para
  uma `Conta` com `tipo == cartao_credito` (ver seção 2). Caso contrário,
  422: `"Pagamento no crédito exige uma conta do tipo cartão."`
- Quando `forma_pagamento` é `DEBITO`, `PIX`, `DINHEIRO` ou `None`:
  `conta_id` **precisa** apontar para uma `Conta` com `tipo == corrente`.
  Caso contrário, 422: `"Esta forma de pagamento não se aplica a um
  cartão de crédito."`

Isso muda a assinatura de `validar_coerencia`: hoje ela recebe
`conta_id`/`conta_destino_id` como inteiros; passa a receber (ou o router
passa a resolver antes) o **tipo** de cada conta envolvida, porque a
validação depende do tipo, não só da existência. Os três chamadores
(`LancamentoBase.model_validator`, `routers/lancamentos.py::atualizar`,
`routers/importacao.py::confirmar`) precisam buscar a `Conta` (já fazem
`_validar_conta` hoje — passa a devolver/checar o tipo também).

### Endpoints afetados

- `POST/PATCH /anos/{ano}/lancamentos` — aceitam `forma_pagamento`.
- `POST /anos/{ano}/importacao/ofx/confirmar` — `TransacaoConfirmar` aceita
  `forma_pagamento` (opcional; o extrato bancário não informa isso, então a
  prévia nunca sugere um valor — o usuário escolhe na revisão se quiser).
- `POST/PATCH /anos/{ano}/gastos-fixos` — aceitam `forma_pagamento`.

### Telas afetadas

- **`FormularioLancamento.tsx`**: novo `<select>` "Forma de pagamento",
  visível só quando `tipo === 'saida'`, com as 4 opções + espaço em branco
  = "não informado". Pré-selecionado em "Débito" (ver ADR-0001 sobre por
  que o backend aceita nulo mesmo assim). Ao escolher "Crédito", o
  `<select>` de conta passa a listar só cartões; nas outras opções, só
  contas correntes (ver seção 2).
- **`TabelaLancamentos.tsx`**: nova coluna/badge mostrando a forma de
  pagamento de cada lançamento (ícone ou texto curto — 💳 crédito, 💵
  dinheiro, etc.), para o usuário conferir de relance sem abrir o item.
- **`ImportarExtrato.tsx`**: campo opcional na revisão de cada transação.
- **`GastosFixos.tsx`**: mesmo `<select>` do formulário de lançamento, com
  a mesma regra de filtrar contas por tipo.

### Critérios de aceite

- Lançamento de saída no crédito não permite escolher uma conta corrente,
  e vice-versa.
- Lançamentos antigos (sem o campo) continuam somando no saldo exatamente
  como somavam antes da mudança — nenhuma migração de dado, só de schema.
- Editar um lançamento de saída trocando a forma de pagamento para
  "crédito" sem trocar a conta é rejeitado com 422 se a conta atual não for
  um cartão (evita um PATCH deixar o dado inconsistente, mesmo padrão que
  `_validar_coerencia` já aplica hoje para `destino`/`categoria`).

---

## 2. Contas e cartões de crédito

### Modelo

```python
class TipoConta(str, enum.Enum):
    CORRENTE = "corrente"
    CARTAO_CREDITO = "cartao_credito"
```

`Conta` ganha:

```python
tipo: Mapped[TipoConta] = mapped_column(
    Enum(TipoConta, native_enum=False), nullable=False, default=TipoConta.CORRENTE
)
# Só relevante para tipo=cartao_credito:
dia_vencimento_fatura: Mapped[int | None] = mapped_column(Integer, nullable=True)
conta_pagamento_padrao_id: Mapped[int | None] = mapped_column(
    ForeignKey("contas.id", ondelete="SET NULL"), nullable=True
)
```

`CheckConstraint` nova: `dia_vencimento_fatura BETWEEN 1 AND 31` quando não
nulo (mesmo padrão de `GastoFixo.dia_vencimento`).

Validação em `ContaCriar`/`ContaAtualizar` (nível de aplicação, já que
SQLite não valida CHECK condicional entre colunas com facilidade):
`tipo == cartao_credito` exige `dia_vencimento_fatura` preenchido;
`tipo == corrente` exige que `dia_vencimento_fatura` e
`conta_pagamento_padrao_id` sejam nulos.

### Endpoints afetados

Reaproveita **os mesmos** `routers/contas.py` — não há endpoint novo além
do que já existe. Muda o schema:

- `ContaCriar`/`ContaAtualizar`/`ContaOut` ganham `tipo`,
  `dia_vencimento_fatura`, `conta_pagamento_padrao_id`.
- `GET /contas` ganha filtro opcional `?tipo=corrente|cartao_credito` (o
  frontend usa isso para preencher os dois seletores diferentes — contas
  reais no formulário de lançamento comum, cartões quando a forma de
  pagamento é crédito).
- `DELETE /contas/{id}`: a regra de "desativar em vez de apagar quando em
  uso" já existente passa a olhar também `FaturaMensal` (ver seção 4), não
  só `Lancamento`/`GastoFixo`.

### Telas afetadas

- **`GerenciadorContas.tsx`**: o formulário de "+ Nova" ganha um seletor
  Conta / Cartão de crédito. Quando "Cartão de crédito", aparecem os campos
  "dia do vencimento" e, opcionalmente, "conta que paga por padrão"
  (`<select>` das contas correntes existentes). A lista passa a ter duas
  seções — "Contas" (como hoje: saldo, guardado, patrimônio somado) e
  "Cartões de crédito" (fatura em aberto, vencimento — ver seção 4). O
  patrimônio total exibido **não inclui** os cartões (ver seção 3).
- **`FormularioLancamento.tsx`** e **`ImportarExtrato.tsx`**: o `<select>`
  de conta filtra por `tipo` conforme a combinação tipo+forma de pagamento
  (regra completa no ADR-0002).

### Critérios de aceite

- Criar uma conta corrente hoje continua funcionando sem mudar nada no uso
  (os campos novos são opcionais/tipados com default).
- Criar um cartão sem dia de vencimento é rejeitado com 422.
- Uma conta corrente não aceita `dia_vencimento_fatura` nem
  `conta_pagamento_padrao_id` preenchidos.
- Editar o dia de vencimento de um cartão já existente (`PATCH /contas/{id}`)
  funciona sem endpoint novo.

---

## 3. Saldo inteligente

Não é uma feature isolada — é a consequência visível de rotear compras no
crédito para a conta-cartão (ADR-0002). O trabalho aqui é **conferir e, onde
necessário, filtrar** cada lugar que soma "quanto eu tenho", para que
cartões (dívida) não se misturem com contas (dinheiro disponível).

### `services/calculos.py`

Nenhuma mudança de fórmula: `calcular_totais_mes` já isola por
`conta_id`. A mudança é em quem **lê** `TotaisMes.por_conta` depois:

- `TotaisMes.saldo` (soma de todas as contas) hoje soma literalmente tudo
  em `por_conta`. Passa a exigir que quem monta `por_conta` só inclua
  contas do tipo `corrente` nessa propriedade — **ou**, alternativa mais
  simples de implementar sem duplicar `Carteiras`: `calcular_totais_mes`
  passa a receber o mapa `conta_id -> TipoConta` (ou já vem junto com os
  lançamentos) e separa internamente `por_conta` (só correntes,
  alimenta `saldo`/`guardado_acumulado` como hoje) de um novo
  `por_cartao: dict[int, Decimal]` (saldo de cada conta-cartão, sempre
  ≤ 0). Ver "Decisão de implementação" abaixo.
- `total_guardado_geral` não muda — guardado nunca existe em cartão.

**Decisão de implementação:** estender `TotaisMes` com `por_cartao:
dict[int, Carteiras]`, espelhando `por_conta`, em vez de misturar os dois
num dicionário só com um filtro por fora. Motivo: evita que um bug de
filtro esquecido em um dos vários lugares que iteram `por_conta` (frontend
incluso) volte a somar dívida como saldo — a separação já vem pronta de
dentro do cálculo, o consumidor não pode errar por omissão.

### `schemas.py`

`ResumoMesOut`/`ResumoAnoOut` ganham `por_cartao: list[CarteirasContaOut]`
ao lado de `por_conta` (mesmo formato — reaproveita `CarteirasContaOut`,
só que `guardado` é sempre `"0.00"` e `saldo` é sempre ≤ 0 ali).

### Telas afetadas

- **`TotaisMes.tsx`**: o "Saldo" em destaque continua sendo só a soma das
  contas correntes (já é assim hoje, sem mudança de comportamento — muda
  só a garantia de que cartões nunca entram nessa soma, mesmo depois de
  existirem).
- **`GerenciadorContas.tsx`**: como descrito na seção 2, "Patrimônio" soma
  só `por_conta`; a seção "Cartões de crédito" mostra `por_cartao`
  separadamente, com o valor **positivo** (`-saldo`) rotulado como "fatura
  em aberto" (ou "crédito a seu favor", se por algum motivo o saldo for
  positivo — ex.: pagamento maior que a fatura).
- Novo texto de apoio, algo como *"Saldo disponível — compras no crédito
  entram na fatura, não descontam daqui até você pagá-la."* — resposta
  direta ao "quero ver o valor que tem no saldo mesmo" do pedido original.

### Critérios de aceite

- Registrar uma saída de R$100 no crédito não muda o `saldo` da conta
  corrente nem o `saldo` agregado do mês — só aparece em `por_cartao`.
- Registrar a mesma saída no débito/pix/dinheiro desconta o saldo
  imediatamente, como hoje.
- O patrimônio mostrado em `GerenciadorContas` bate com a soma de
  `saldo + guardado` só das contas do tipo `corrente`.

---

## 4. Fatura do cartão de crédito

### Modelo

```python
class FaturaMensal(Base):
    __tablename__ = "faturas_mensais"
    __table_args__ = (
        UniqueConstraint("cartao_id", "ano_id", "mes", name="uq_fatura_cartao_ano_mes"),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_fatura_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cartao_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ano_id: Mapped[int] = mapped_column(
        ForeignKey("anos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    situacao: Mapped[SituacaoGastoFixo] = mapped_column(
        Enum(SituacaoGastoFixo, native_enum=False),
        nullable=False, default=SituacaoGastoFixo.PENDENTE,
    )
    lancamento_id: Mapped[int | None] = mapped_column(
        ForeignKey("lancamentos.id", ondelete="SET NULL"), nullable=True
    )
```

Reaproveita o enum `SituacaoGastoFixo` (`pendente`/`pago`) — mesmo
significado, não faz sentido um terceiro enum idêntico.

### Endpoints novos

`backend/app/routers/faturas.py`, prefixo
`/anos/{ano}/cartoes/{cartao_id}/fatura` (mesmo molde de
`routers/gastos_fixos.py`):

- `GET /` — devolve o valor em aberto do mês corrente (reaproveitando
  `calcular_ano`, buscando `por_cartao[cartao_id].saldo` do mês pedido) e a
  situação (`FaturaMensal`, se existir; senão implicitamente pendente).
- `POST /{mes}/pagar` — corpo opcional `{ "conta_pagamento_id": int | null }`.
  1. Calcula o valor em aberto do cartão naquele mês (via
     `services/calculos.py`, sem duplicar a soma).
  2. Se já existe `FaturaMensal` paga para esse mês, devolve o lançamento
     existente (idempotente, igual a `gastos_fixos.py::pagar`).
  3. Cria um `Lancamento` `TRANSFERENCIA`: `conta_id = conta_pagamento_id ou
     Conta(cartao).conta_pagamento_padrao_id` (422 se nenhum dos dois
     existir — não há como pagar sem saber de onde sai o dinheiro),
     `conta_destino_id = cartao_id`, `valor = fatura em aberto`.
  4. Marca `FaturaMensal.situacao = pago`, guarda `lancamento_id`.
- `POST /{mes}/desfazer` — apaga o lançamento gerado, volta a `pendente`.
  Mesmo comportamento de `gastos_fixos.py::desfazer`.

### Telas afetadas

- **`GerenciadorContas.tsx`** (seção "Cartões de crédito"): cada cartão
  mostra fatura em aberto, "vence dia N" e um botão "Marcar fatura como
  paga" (abre um mini-formulário para escolher a conta pagadora, já
  vindo preenchida com `conta_pagamento_padrao_id` quando existir).
- **`CalendarioVencimentos.tsx`**: recebe uma prop nova `cartoes` (lista de
  cartões ativos + fatura em aberto do mês) e plota, no dia
  `dia_vencimento_fatura`, um marcador do vencimento da fatura — visual
  distinto do gasto fixo (cor/ícone próprios, ex.: 💳), mesmo texto de apoio
  ("clique para alternar"). Clicar chama `pagar`/`desfazer` como os gastos
  fixos já fazem.
- Título do card do calendário deixa de ser só "Vencimentos de {mês}" e
  passa a cobrir os dois tipos de vencimento — copy a definir, ex.: "o que
  vence em {mês}".

### Critérios de aceite

- Pagar a fatura duas vezes seguidas não duplica o lançamento nem desconta
  o saldo da conta pagadora duas vezes.
- Desfazer o pagamento remove o lançamento gerado e volta a fatura a
  aparecer como pendente no calendário.
- Editar `dia_vencimento_fatura` do cartão (`PATCH /contas/{id}`) muda
  onde o lembrete aparece no calendário do mês seguinte para a frente,
  sem reescrever meses já fechados.
- Um cartão sem `conta_pagamento_padrao_id` ainda pode ter a fatura paga,
  desde que a conta seja informada explicitamente na chamada.

---

## Fora de escopo (explicitamente, para não crescer sozinho)

- Dia de **fechamento** da fatura (distinto do vencimento) — ver ADR-0003.
- Limite de crédito e alerta de limite.
- Parcelamento de compra no crédito (uma compra parcelada em N lançamentos
  futuros).
- Juros/multa por atraso de fatura.

Se algum desses for pedido depois, encaixa como extensão do que está aqui
(mais um campo em `Conta`, ou um novo tipo de `Lancamento`), não como
mudança de arquitetura.
