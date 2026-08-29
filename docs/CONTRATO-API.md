# Contrato de API — forma de pagamento, cartões, saldo inteligente, fatura e layout

Este documento existe para separar o trabalho em **duas conversas
independentes** (backend e frontend) sem que elas precisem se coordenar em
tempo real. É a fonte da verdade sobre **o que a API expõe** — o backend
implementa exatamente isto, o frontend consome exatamente isto. Detalhe de
*por quê* cada decisão foi tomada continua nos ADRs (`docs/adr/`) e nas
specs por rodada (`docs/specs/`); este documento só junta, num lugar só, a
superfície de contrato das duas rodadas já especificadas.

Se alguma dúvida aparecer durante a implementação sobre um campo que não
está aqui, é sinal de que o contrato precisa ser atualizado **antes** de
qualquer um dos dois lados codificar em cima do palpite — evita que
backend e frontend divirjam silenciosamente.

---

## Enums

```python
class FormaPagamento(str, enum.Enum):
    CREDITO = "credito"
    DEBITO = "debito"
    PIX = "pix"
    DINHEIRO = "dinheiro"

class TipoConta(str, enum.Enum):
    CORRENTE = "corrente"
    CARTAO_CREDITO = "cartao_credito"

# Já existe, reaproveitado por FaturaMensal:
class SituacaoGastoFixo(str, enum.Enum):
    PENDENTE = "pendente"
    PAGO = "pago"
```

```ts
export type FormaPagamento = 'credito' | 'debito' | 'pix' | 'dinheiro';
export type TipoConta = 'corrente' | 'cartao_credito';
```

---

## `Conta`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | `int` | — (saída) | |
| `nome` | `string` | sim | já existe |
| `cor` | `string` (`#rrggbb`) | não (default) | já existe |
| `ordem` | `int` | não (default `0`) | já existe |
| `ativa` | `bool` | — (saída) | já existe |
| `tipo` | `TipoConta` | não (default `corrente`) | **novo** |
| `dia_vencimento_fatura` | `int \| null` (1–31) | sim quando `tipo=cartao_credito`; deve ser `null` quando `tipo=corrente` | **novo** |
| `conta_pagamento_padrao_id` | `int \| null` | opcional, só relevante quando `tipo=cartao_credito`; deve ser `null` quando `tipo=corrente` | **novo** |

- `POST /contas` e `PATCH /contas/{id}`: aceitam os 3 campos novos, com a
  validação cruzada acima (422 se violada).
- `GET /contas`: ganha query param opcional `?tipo=corrente|cartao_credito`.
  Sem o param, devolve todas (como hoje).
- `DELETE /contas/{id}`: comportamento inalterado (desativa se em uso —
  agora "em uso" também considera `FaturaMensal`, não só `Lancamento`/`GastoFixo`).

---

## `Lancamento`

| Campo | Tipo | Observação |
| --- | --- | --- |
| *(todos os campos atuais, inalterados)* | | ver `types/api.ts` hoje |
| `forma_pagamento` | `FormaPagamento \| null` | **novo**. Só aceito quando `tipo=saida` (422 nos demais tipos). `null` é válido e tratado como `debito`. |

Regra de validação nova (`POST`/`PATCH /anos/{ano}/lancamentos`, e também
em `POST /anos/{ano}/importacao/ofx/confirmar`):

- `forma_pagamento=credito` ⇒ `conta_id` deve referenciar uma `Conta` com
  `tipo=cartao_credito`. Senão: `422 "Pagamento no crédito exige uma conta
  do tipo cartão."`
- `forma_pagamento` em `debito`/`pix`/`dinheiro`/ausente ⇒ `conta_id` deve
  referenciar uma `Conta` com `tipo=corrente`. Senão: `422 "Esta forma de
  pagamento não se aplica a um cartão de crédito."`
- Tipos diferentes de `saida` (`entrada`, `guardado`, `retirado`,
  `rendimento`, `perda`) sempre exigem `conta_id` do tipo `corrente`.
- `transferencia`: `conta_id` (origem) sempre `corrente`; `conta_destino_id`
  pode ser `corrente` (transferência comum) **ou** `cartao_credito`
  (pagamento de fatura — ver seção `FaturaMensal` abaixo, que é quem cria
  esse lançamento; criar manualmente também é permitido e válido).

---

## `GastoFixo`

| Campo | Tipo | Observação |
| --- | --- | --- |
| `forma_pagamento_legado` | `string` | **renomeado** do atual `forma_pagamento` (texto livre). Só leitura/histórico, nenhuma regra nova o usa. |
| `forma_pagamento` | `FormaPagamento \| null` | **novo**, mesmo enum e mesma regra de compatibilidade com `conta_id` que `Lancamento` (ver acima). |

`conta_id` de `GastoFixo` passa a poder referenciar um cartão — nesse
caso, o lançamento gerado por `POST .../meses/{mes}/pagar` nasce com
`forma_pagamento=credito` e vai para a conta-cartão, não para uma conta
real (mesma regra de sempre: `pagar` gera o lançamento; não muda a
assinatura desse endpoint, só o resultado).

---

## `ResumoMesOut` / `ResumoAnoOut`

Campo novo em ambos: `por_cartao: CarteirasContaOut[]` — mesmo formato de
`por_conta`, mas só com contas `tipo=cartao_credito`. Nelas, `guardado` é
sempre `"0.00"`, e `saldo` é sempre `≤ "0.00"` (dívida). A leitura para a
interface: **fatura em aberto = `-saldo`** (se `saldo` for positivo por
algum motivo — ex.: pagamento maior que a fatura — trate como crédito a
favor, não como fatura a pagar).

`por_conta` (o campo que já existe) passa a conter **só** contas
`tipo=corrente` — cartões saem dali e vão para `por_cartao`. Isso muda o
que já é consumido hoje por `GerenciadorContas.tsx`/`TotaisMes.tsx`: o
"saldo"/"patrimônio" agregado continua correto sem filtro nenhum do lado
do frontend, porque o backend já garante a separação.

---

## `FaturaMensal` — endpoints novos

Prefixo: `/anos/{ano}/cartoes/{cartao_id}/fatura`

### `GET /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}`

> **Corrigido em relação ao rascunho.** O mês vai no caminho, não em
> `?mes=`. É o que o backend implementa e o que já está em produção, e casa
> com `pagar`/`desfazer` logo abaixo, que sempre foram assim — usar query
> param só no `GET` deixaria os três inconsistentes entre si.

Resposta:

```ts
interface FaturaOut {
  cartao_id: number;
  ano: number;
  mes: number;
  valor_em_aberto: string;      // Decimal como string, igual ao resto da API
  situacao: 'pendente' | 'pago';
  lancamento_id: number | null; // preenchido se `situacao=pago`
  dia_vencimento: number;       // espelha `Conta.dia_vencimento_fatura`, pra conveniência do calendário
}
```

### `POST /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/pagar`

Corpo (opcional):

```ts
{ conta_pagamento_id?: number | null }
```

- Se omitido, usa `Conta(cartao).conta_pagamento_padrao_id`.
- Se nenhum dos dois existir: `422 "Informe de qual conta a fatura será paga."`
- Idempotente: chamar de novo com a fatura já paga devolve **o mesmo
  lançamento**, sem duplicar nada.

  > **Corrigido em relação ao rascunho**, que dizia `200` na segunda chamada.
  > A resposta é `201` nas duas vezes — o status vem fixo do decorador da
  > rota. Conferido na execução da Fase 3, e vale igual para
  > `gastos-fixos/.../pagar`. Não muda nada para quem consome (mesmo corpo,
  > ambos 2xx); se um dia o rigor de REST importar, distinguir criado de
  > já-existente é uma mudança de código pequena, mas seria uma mudança de
  > comportamento em produção, então fica registrada e não feita.
- Resposta: `LancamentoOut` do lançamento `transferencia` criado (ou já
  existente).

### `POST /anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/desfazer`

- Sem corpo. `204 No Content`. Apaga o lançamento gerado, volta
  `situacao=pendente`.

---

## Preferência de layout do dashboard

### `GET /preferencias/layout-dashboard`

Resposta:

```ts
interface LayoutDashboardOut {
  layout: string | null; // JSON serializado (ver schema ItemLayout[] na spec do frontend) — o backend não valida o conteúdo, só guarda e devolve
}
```

`null` quando o usuário nunca salvou um layout.

### `PUT /preferencias/layout-dashboard`

Corpo:

```ts
{ layout: string } // JSON serializado, formato livre do lado do frontend
```

Resposta: **`LayoutDashboardOut` (eco do que foi salvo) — decidido.** O
rascunho deixava `204` em aberto; ficou o eco porque mantém o mesmo formato
do `GET`, então o frontend pode usar a resposta do `PUT` diretamente como
novo estado, sem uma segunda chamada para reler.

Ambos os endpoints exigem sessão (herdam a dependência global de auth do
`main.py`, como todo o resto da API) e não pertencem a `/anos/{ano}/...` —
é uma preferência do usuário, não do ano.

O layout é **por usuário**: dois usuários diferentes têm layouts
independentes, e um nunca vê o do outro. Isso o diferencia das cores da
forma de pagamento abaixo, que são globais.

---

## Cores da forma de pagamento

> **Não estava no rascunho deste contrato.** Foi implementado numa rodada
> anterior, já está em produção, e o frontend já consome — está aqui para o
> contrato refletir a API de verdade.

Puramente cosmético: muda só a cor com que o rótulo da forma de pagamento
aparece na interface, nunca um dado financeiro. Fica no servidor, e não em
`localStorage`, para a escolha aparecer igual no celular e no PC.

**Global, não por usuário** — as quatro formas de pagamento são fixas para
o app inteiro. (Contraste com o layout do painel, logo acima.)

### `GET /preferencias/cores-forma-pagamento`

Devolve sempre as quatro formas, na ordem `dinheiro`, `debito`, `pix`,
`credito` — as que ainda não foram personalizadas vêm com a cor padrão:

```ts
type CorPagamentoOut = {
  forma_pagamento: FormaPagamento;
  cor: string; // '#rrggbb'
}[];
```

Padrões: `dinheiro` `#22c55e`, `debito` `#0ea5e9`, `pix` `#14b8a6`,
`credito` `#f97316`.

### `PUT /preferencias/cores-forma-pagamento/{forma_pagamento}`

Corpo: `{ cor: string }` (`#rrggbb`, validado — 422 fora do formato).
Resposta: o registro salvo (`{ forma_pagamento, cor }`).

---

## Perfil (ADR-06)

`GET /auth/eu` **ganhou dois campos** — quem já consome precisa saber:

```ts
interface UsuarioOut {
  id: number;
  email: string;
  nome: string | null;          // novo. null = nunca preencheu; usar o e-mail
  alertas_email_ativo: boolean; // novo. ver aviso abaixo
}
```

### `PATCH /auth/eu`

Corpo parcial: `{ nome?: string | null, alertas_email_ativo?: boolean }`.
Resposta: `UsuarioOut`. Só mexe em quem está logado — não recebe id.

Nome só com espaços vira `null`: "nunca preencheu" e "apagou" são o mesmo
estado.

> ⚠️ **`alertas_email_ativo` ainda não faz nada.** O backend não envia e-mail
> — não há serviço de envio nem processo agendado (ADR-06, seção 4). O campo
> existe para a preferência já ter onde morar. **O toggle não deve aparecer na
> interface enquanto isso não for implementado**, para não repetir o problema
> da seção 6 da Parte 1: um controle que parece funcionar e não funciona.

---

## Metas de poupança (ADR-06)

Duas formas, que podem estar ativas ao mesmo tempo: `mensal` (hábito, medido
contra o guardado do mês) e `prazo` (objetivo, medido contra o acumulado).

**No máximo uma ativa por tipo.** Criar uma nova do mesmo tipo desativa a
anterior automaticamente — ela vira histórico, não é apagada.

```ts
type TipoMetaPoupanca = 'mensal' | 'prazo';

interface MetaPoupancaOut {
  id: number;
  tipo: TipoMetaPoupanca;
  valor_alvo: string;        // Decimal como string
  data_alvo: string | null;  // "YYYY-MM-DD"; só em tipo='prazo'
  criada_em: string;
  ativa: boolean;
}
```

| Método | Rota | Observação |
| --- | --- | --- |
| `GET` | `/metas-poupanca` | Ativas; `?incluir_inativas=true` traz o histórico |
| `POST` | `/metas-poupanca` | `{ tipo, valor_alvo, data_alvo? }` → `201` |
| `GET` | `/metas-poupanca/ativas` | Com progresso calculado (abaixo) |
| `DELETE` | `/metas-poupanca/{id}` | `204`; desativa, não apaga |

Validação: `prazo` **exige** `data_alvo`; `mensal` **recusa** `data_alvo`
(`422` com a frase pronta, nos dois casos). `valor_alvo` tem de ser > 0.

### `GET /metas-poupanca/ativas`

```ts
interface MetasAtivasOut {
  mensal: {
    id: number;
    valor_alvo: string;
    guardado_no_mes: string;
    percentual: number;   // pode passar de 100; nunca negativo
  } | null;
  prazo: {
    id: number;
    valor_alvo: string;
    data_alvo: string;
    guardado_acumulado: string;
    percentual: number;
    dias_restantes: number;  // negativo se a data já passou
  } | null;
}
```

O progresso é calculado **no backend** — o frontend não deve recalcular, senão
os dois números divergem. Mas os dois tipos medem coisas diferentes:

- **`mensal`** olha o `guardado_no_mes` do **mês corrente**, o mesmo número que
  `GET /anos/{ano}/resumo` traz para aquele mês. Medido contra o ano corrente;
  se ele ainda não existe no sistema, vem zerado em vez de erro.
- **`prazo`** conta só o que foi guardado **a partir do dia em que a meta foi
  criada** — não o total da reserva. Uma meta nova nasce em 0%, mesmo com a
  reserva cheia: quem já tem R$ 13 mil guardados e decide juntar R$ 6 mil não
  está com a meta concluída. Retiradas descontam do progresso.

---

## Alertas de vencimento (ADR-06)

### `GET /alertas`

Gastos fixos e faturas de cartão que vencem nos **próximos 3 dias** e ainda
não foram pagos. Janela fixa nesta versão, não configurável.

**São dois formatos**, distinguidos por `tipo` — não um formato único com
campos opcionais. Os nomes dos campos seguem o vocabulário que cada origem já
tem no resto da API: `dia_vencimento` é do gasto fixo, `dia_vencimento_fatura`
é do cartão, e eles significam coisas diferentes. Achatá-los num nome só criaria
um vocabulário que valeria apenas nesta rota.

```ts
interface AlertaGastoFixoOut {
  tipo: 'gasto_fixo';
  gasto_fixo_id: number;
  nome: string;
  dia_vencimento: number;
  dias_restantes: number;   // 0 = vence hoje; nunca negativo
  valor: string;
}

interface AlertaFaturaOut {
  tipo: 'fatura';
  cartao_id: number;
  nome_cartao: string;
  dia_vencimento_fatura: number;
  dias_restantes: number;
  valor: string;            // valor em aberto, igual ao do endpoint da fatura
}

type AlertaOut = AlertaGastoFixoOut | AlertaFaturaOut;
```

No OpenAPI isso sai como `oneOf` com `discriminator: tipo`, então o
estreitamento de tipo em TypeScript funciona direto:
`if (alerta.tipo === 'fatura') { alerta.nome_cartao }`.

Ordenado por urgência (o que vence antes vem primeiro). Não há tabela de
alertas: é calculado na hora, a partir dos dias de vencimento e do que já
consta como pago no mês.

Três comportamentos que valem saber:

- **O que já venceu não aparece.** O que fazer com uma conta atrasada (por
  quanto tempo insistir, como sinalizar) é outra decisão, ainda não tomada.
- **Fatura zerada não vira alerta.** Sem valor em aberto não há o que pagar, e
  `.../fatura/{mes}/pagar` recusaria a operação — avisar ali ofereceria uma
  ação impossível.
- **O `valor` da fatura é o mesmo que `GET .../fatura/{mes}` devolve** em
  `valor_em_aberto`. Sai do mesmo cálculo; se os dois divergirem, é bug.

Se o ano corrente ainda não foi criado, devolve lista vazia.

---

## Resumo — tabela de todos os endpoints desta e da rodada anterior

| Método | Rota | Novo ou alterado | Depende de |
| --- | --- | --- | --- |
| `POST`/`PATCH` | `/anos/{ano}/lancamentos` | alterado — `forma_pagamento` | `TipoConta` já existir |
| `POST` | `/anos/{ano}/importacao/ofx/confirmar` | alterado — `forma_pagamento` opcional | idem |
| `POST`/`PATCH` | `/anos/{ano}/gastos-fixos` | alterado — `forma_pagamento` | idem |
| `GET`/`POST`/`PATCH`/`DELETE` | `/contas` | alterado — `tipo`, `dia_vencimento_fatura`, `conta_pagamento_padrao_id`, filtro `?tipo=` | — |
| `GET` | `/anos/{ano}/resumo` | alterado — `por_cartao` em cada mês/ano | `Conta.tipo` + roteamento de crédito |
| `GET` | `/anos/{ano}/cartoes/{cartao_id}/fatura/{mes}` | **novo** | `por_cartao` calculado |
| `POST` | `/anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/pagar` | **novo** | idem |
| `POST` | `/anos/{ano}/cartoes/{cartao_id}/fatura/{mes}/desfazer` | **novo** | idem |
| `GET`/`PUT` | `/preferencias/layout-dashboard` | **novo** | independente de tudo acima |
| `GET` | `/preferencias/cores-forma-pagamento` | **novo** | independente de tudo acima |
| `PUT` | `/preferencias/cores-forma-pagamento/{forma_pagamento}` | **novo** | idem |
| `GET` | `/auth/eu` | alterado — `nome`, `alertas_email_ativo` | ADR-06 |
| `PATCH` | `/auth/eu` | **novo** | idem |
| `GET`/`POST` | `/metas-poupanca` | **novo** | idem |
| `GET` | `/metas-poupanca/ativas` | **novo** | agregação de `guardado` já existente |
| `DELETE` | `/metas-poupanca/{id}` | **novo** | idem |
| `GET` | `/alertas` | **novo** | `dia_vencimento` de gastos fixos e cartões |

---

## O que este contrato não cobre (de propósito)

Widgets do modo estático que não fazem chamada própria (ex.: "despesas
diárias reais", calculado no cliente a partir de `GET
/anos/{ano}/lancamentos` que já existe) não aparecem aqui — não mudam a
API, só como o frontend usa o que já existe. Ver
`docs/specs/modo-painel-e-widgets.md` para a lista completa.
