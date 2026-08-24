# Referência da API

Base: `http://localhost:8000`

A documentação interativa gerada pelo FastAPI, onde é possível testar cada
chamada pelo navegador, fica em `/docs`. Este arquivo resume o contrato.

## Convenções

- Valores monetários trafegam como **string decimal** (`"1234.56"`), nunca como
  número — ver [ARQUITETURA.md](ARQUITETURA.md#por-que-decimal-e-não-float).
- Datas em ISO 8601 (`"2026-04-06"`).
- **Todo** erro retorna `{"detail": "mensagem em português"}` — de negócio, de
  validação ou inesperado, sempre no mesmo formato (ver
  [ADR-01](adr/ADR-01-contrato-api-e-tratamento-erros.md)). Quem consome lê
  sempre o mesmo campo, sem precisar saber de onde o erro veio.

| Código | Significado |
| --- | --- |
| 404 | Recurso não existe |
| 409 | Conflito: duplicado ou ano arquivado |
| 422 | Dados inválidos |
| 500 | Erro inesperado; a causa fica no log do servidor, não na resposta |

Erros de validação (`422`) trazem, além de `detail`, um campo `campos` com
`[{campo, mensagem}]` — útil para o formulário destacar o que falhou. É
opcional: `detail` sozinho já serve para exibir um aviso.

```json
{
  "detail": "Transferência exige a conta de destino.",
  "campos": [{"campo": "conta_destino_id", "mensagem": "..."}]
}
```

## Anos

### `GET /anos`
Lista todos os anos, inclusive arquivados, do mais recente para o mais antigo.

### `POST /anos`
```json
{ "ano": 2026, "saldo_inicial_conta": "0.97", "saldo_inicial_guardado": "7867.36" }
```
Os saldos são opcionais (padrão `0`). Retorna 409 se o ano já existir.

### `POST /anos/{ano}/arquivar`
Torna o ano somente-leitura e cria o seguinte com os saldos de fechamento como
abertura. Retorna 409 se já estiver arquivado.

### `POST /anos/{ano}/desarquivar`
Reabre o ano para edição.

### `GET /anos/{ano}/resumo`
Devolve, em uma única chamada, tudo que as 12 páginas precisam:

```json
{
  "ano": 2026,
  "arquivado": false,
  "total_guardado": "13041.83",
  "saldo_final": "-387.59",
  "total_entradas": "12494.81",
  "total_saidas": "7876.06",
  "meses": [
    {
      "mes": 4,
      "nome_mes": "abril",
      "entradas": "2390.00",
      "saidas": "1727.19",
      "guardado_no_mes": "634.03",
      "saldo": "39.78",
      "saldo_inicial": "0.97",
      "guardado_acumulado": "8501.39",
      "gastos_por_categoria": [
        { "categoria": "Comida", "total": "738.11", "percentual": 42.7 }
      ]
    }
  ]
}
```

`meses` sempre traz 12 itens, mesmo os vazios.

## Lançamentos

### `GET /anos/{ano}/lancamentos`
Parâmetros opcionais: `mes` (1–12), `tipo`, `categoria_id`.

### `POST /anos/{ano}/lancamentos`
```json
{
  "data": "2026-04-06",
  "valor": "2000.00",
  "tipo": "entrada",
  "descricao": "salário"
}
```

O campo `mes` **não** é aceito: é derivado da data.

Para rendimentos, `destino` é obrigatório:
```json
{ "data": "2026-06-16", "valor": "47.75", "tipo": "rendimento", "destino": "guardado" }
```

Para saídas, `categoria_id` e `forma_pagamento` são opcionais:
```json
{ "data": "2026-06-09", "valor": "8.50", "tipo": "saida", "categoria_id": 1, "forma_pagamento": "pix", "descricao": "brownie" }
```

`forma_pagamento` (`credito | debito | pix | dinheiro`) só é aceito em saídas.
`credito` exige que `conta_id` seja um cartão; as demais formas (e a ausência
do campo) exigem uma conta corrente — ver
[REGRAS.md](REGRAS.md#forma-de-pagamento).

### `PATCH /anos/{ano}/lancamentos/{id}`
Atualização parcial. Só os campos enviados mudam.

### `DELETE /anos/{ano}/lancamentos/{id}`
Retorna 204.

## Contas e cartões de crédito

Um cartão de crédito é uma `Conta` com `tipo=cartao_credito` (ver
[ARQUITETURA.md](ARQUITETURA.md#forma-de-pagamento-cartões-de-crédito-e-fatura)).

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/contas` | Lista as ativas; `?tipo=corrente\|cartao_credito` filtra; `?incluir_inativas=true` traz todas |
| `POST` | `/contas` | `{ "nome": "Nubank" }` ou `{ "nome": "Cartão X", "tipo": "cartao_credito", "dia_vencimento_fatura": 10 }` |
| `PATCH` | `/contas/{id}` | Atualização parcial |
| `DELETE` | `/contas/{id}` | Desativa se em uso (lançamento, gasto fixo ou fatura); remove se não |

Um cartão exige `dia_vencimento_fatura` (1–31); uma conta corrente não aceita
`dia_vencimento_fatura` nem `conta_pagamento_padrao_id` preenchidos.

## Fatura do cartão de crédito

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/anos/{ano}/cartoes/{cartao_id}/fatura/{mes}` | Valor em aberto e situação (recalculado, nunca armazenado) |
| `POST` | `.../fatura/{mes}/pagar` | Corpo opcional `{ "conta_pagamento_id": int }`; gera a transferência (idempotente) |
| `POST` | `.../fatura/{mes}/desfazer` | Remove a transferência gerada, volta a pendente |

Sem `conta_pagamento_id` no corpo, usa `conta_pagamento_padrao_id` do cartão;
sem nenhum dos dois, `pagar` devolve 422. O `GET` traz também
`dia_vencimento`, espelhando o do cartão, para o calendário não precisar
cruzar a resposta com a lista de contas.

## Preferências

Nem por ano, nem financeiras: só mudam como a interface aparece. Ficam no
servidor — e não no navegador — para valerem igual no celular e no PC.

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/preferencias/cores-forma-pagamento` | Cor de cada forma de pagamento (as não personalizadas vêm com o padrão) |
| `PUT` | `/preferencias/cores-forma-pagamento/{forma}` | `{ "cor": "#22c55e" }` |
| `GET` | `/preferencias/layout-dashboard` | `{ "layout": string \| null }`; `null` = nunca arrumou o painel |
| `PUT` | `/preferencias/layout-dashboard` | `{ "layout": string }`; responde com o que ficou salvo |

As cores são **globais** (as quatro formas de pagamento são fixas para o app
inteiro); o layout é **por usuário**. `layout` é texto opaco: JSON gerado e
lido só pelo frontend, que o backend guarda sem validar o conteúdo.

## Categorias

São globais — valem para todos os anos.

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/categorias` | Lista as ativas; `?incluir_inativas=true` traz todas |
| `POST` | `/categorias` | `{ "nome": "Comida", "cor": "#f97316" }` |
| `PATCH` | `/categorias/{id}` | Altera nome, cor ou situação |
| `DELETE` | `/categorias/{id}` | Desativa se estiver em uso; remove se não |

## Gastos fixos

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/anos/{ano}/gastos-fixos` | Lista com a situação de cada mês |
| `POST` | `/anos/{ano}/gastos-fixos` | `{ "descricao": "Internet", "valor": "54.17", "dia_vencimento": 10 }` |
| `PATCH` | `/anos/{ano}/gastos-fixos/{id}` | Atualização parcial |
| `DELETE` | `/anos/{ano}/gastos-fixos/{id}` | Remove o modelo; lançamentos gerados permanecem |
| `POST` | `.../{id}/meses/{mes}/pagar` | Gera o lançamento do mês (idempotente) |
| `POST` | `.../{id}/meses/{mes}/desfazer` | Remove o lançamento gerado |

Aceita `forma_pagamento` (mesmo enum de lançamentos); `conta_id` pode ser um
cartão quando `forma_pagamento=credito`. `forma_pagamento_legado` é o campo de
texto livre de antes do enum existir, mantido só para exibição.

## Wishlist

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/anos/{ano}/wishlist` | Lista os desejos |
| `GET` | `/anos/{ano}/wishlist/total` | Soma dos marcados e total geral |
| `POST` | `/anos/{ano}/wishlist` | `{ "desejo": "Fone", "valor": "300", "importancia": "alta" }` |
| `PATCH` | `/anos/{ano}/wishlist/{id}` | Atualização parcial |
| `DELETE` | `/anos/{ano}/wishlist/{id}` | Remove o item |

## Infraestrutura

### `GET /saude`
```json
{ "status": "ok" }
```
