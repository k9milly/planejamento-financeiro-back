# Referência da API

Base: `http://localhost:8000`

A documentação interativa gerada pelo FastAPI, onde é possível testar cada
chamada pelo navegador, fica em `/docs`. Este arquivo resume o contrato.

## Convenções

- Valores monetários trafegam como **string decimal** (`"1234.56"`), nunca como
  número — ver [ARQUITETURA.md](ARQUITETURA.md#por-que-decimal-e-não-float).
- Datas em ISO 8601 (`"2026-04-06"`).
- Erros retornam `{"detail": "mensagem"}` (ou uma lista, em erros de validação).

| Código | Significado |
| --- | --- |
| 404 | Recurso não existe |
| 409 | Conflito: duplicado ou ano arquivado |
| 422 | Dados inválidos |

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

Para saídas, `categoria_id` é opcional:
```json
{ "data": "2026-06-09", "valor": "8.50", "tipo": "saida", "categoria_id": 1, "descricao": "brownie" }
```

### `PATCH /anos/{ano}/lancamentos/{id}`
Atualização parcial. Só os campos enviados mudam.

### `DELETE /anos/{ano}/lancamentos/{id}`
Retorna 204.

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
