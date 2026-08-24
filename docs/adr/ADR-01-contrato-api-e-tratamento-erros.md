# ADR-01 — Padronização do contrato de API e tratamento global de erros

**Status:** proposto

## Contexto

O backend (`planejamento-financeiro-back`) já expõe uma API funcional, mas
o formato de erro que ela devolve hoje não é único — varia conforme quem
gera o erro:

- Erros de negócio, levantados à mão com `HTTPException(status_code=...,
  detail="mensagem em português")` (ex.: `routers/lancamentos.py`,
  `routers/faturas.py`): corpo `{ "detail": "texto pronto para mostrar ao
  usuário" }`.
- Erros de validação do Pydantic, quando um campo obrigatório falta ou tem
  formato errado (ex.: `valor` negativo, `data` mal formatada): o FastAPI
  gera automaticamente `422` com um corpo **diferente** —
  `{ "detail": [{ "loc": [...], "msg": "...", "type": "..." }, ...] }`, uma
  lista de objetos, em inglês técnico, nunca pensada para aparecer na tela.
- Erros levantados dentro de um `model_validator` do Pydantic (as regras de
  coerência de `LancamentoBase`, por exemplo) também caem no formato de
  lista acima, mesmo sendo, na prática, uma mensagem de negócio em
  português (ex.: "Transferência exige a conta de destino.") — só que
  embrulhada dentro da lista de validação, não como string direta.
- Não há nenhum exception handler global em `main.py` — um erro 500
  inesperado (bug, falha de banco) hoje vaza no formato padrão do
  Starlette, que também difere dos dois casos acima.

Consumido de um frontend acoplado (Jinja/templates, ou o próprio time que
escreve os dois lados ao mesmo tempo), essa inconsistência é inconveniente
mas administrável. Numa arquitetura desacoplada — dois repositórios, dois
times/conversas de implementação diferentes — ela vira um problema real: o
frontend precisaria de três caminhos de tratamento de erro diferentes
(string direta, lista de validação, 500 sem corpo previsível) só para
mostrar uma mensagem na tela, e adivinhar qual caminho se aplica a cada
resposta.

## Decisão

Duas mudanças, as duas só no backend — o frontend não muda seu jeito de
disparar requisições, só como lê o erro de volta:

### 1. Um envelope único para todo erro de negócio (4xx)

Todo `HTTPException` levantado nos routers já usa `detail` como string
pronta para exibição — isso **não muda**. O que muda é garantir que erros
de validação do Pydantic (422) cheguem no mesmo formato, em vez do formato
de lista do FastAPI. Um exception handler para `RequestValidationError` em
`main.py` reduz a lista de erros à primeira mensagem, convertida para uma
frase única:

```python
@app.exception_handler(RequestValidationError)
async def erro_validacao(request: Request, exc: RequestValidationError):
    primeiro = exc.errors()[0]
    mensagem = primeiro.get("msg", "Dados inválidos.")
    # o Pydantic prefixa mensagens de model_validator com "Value error, ";
    # a regra de negócio já escreve a frase pronta, então o prefixo só
    # atrapalha quem for ler.
    if mensagem.startswith("Value error, "):
        mensagem = mensagem.removeprefix("Value error, ")
    return JSONResponse(
        status_code=422,
        content={"detail": mensagem, "campos": [
            {"campo": ".".join(str(p) for p in e["loc"][1:]), "mensagem": e["msg"]}
            for e in exc.errors()
        ]},
    )
```

Resultado: **toda** resposta de erro de negócio, venha de onde vier, tem a
forma `{ "detail": "mensagem em português pronta para mostrar" }`, com um
campo extra opcional `campos` (lista de `{campo, mensagem}`) só para quando
o formulário quiser destacar o campo específico que falhou — o frontend não
é obrigado a usá-lo, `detail` sozinho já é suficiente para o caso comum
(toast de erro).

### 2. Um handler para erro inesperado (500)

> **Corrigido na implementação.** Este ADR previa
> `@app.exception_handler(Exception)`. Não funciona para o caso que interessa:
> esse handler roda dentro do `ServerErrorMiddleware` do Starlette, que fica
> **acima** de todos os middlewares da aplicação, inclusive o de CORS. A
> resposta 500 sai sem `Access-Control-Allow-Origin`, e o navegador esconde a
> mensagem atrás de um erro de CORS genérico — exatamente quando ela mais
> importa, e ainda manda quem for depurar procurar um problema de CORS que não
> existe.
>
> O que foi implementado é um middleware registrado **antes** do
> `CORSMiddleware` (o último a ser adicionado é o mais externo, então este fica
> por dentro e a resposta ainda passa pelo CORS na volta):

```python
@app.middleware("http")
async def erro_inesperado(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logging.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno. Tente novamente em instantes."},
        )
```

Mesma forma `{ "detail": "..." }` — o frontend nunca precisa checar "isto é
um 4xx ou um 5xx" para saber onde procurar a mensagem: é sempre
`response.data.detail` (ou equivalente, ver ADR-02 para onde essa leitura
mora no cliente React Query).

Garantido por `backend/tests/test_erros.py`, que verifica tanto o corpo quanto
a presença do cabeçalho de CORS na resposta 500 — sem esse segundo teste a
regressão passaria despercebida no `pytest` e só apareceria no navegador.

## Por que não um envelope mais rico (RFC 7807 `application/problem+json`, código de erro machine-readable, etc.)

Considerado e rejeitado para este momento. Um `type`/`code` por erro (ex.:
`"CONTA_INCOMPATIVEL_COM_FORMA_PAGAMENTO"`) permitiria ao frontend reagir
programaticamente a erros específicos (destacar um campo, oferecer uma ação
de correção), mas nenhuma tela mapeada na Parte 1 precisa disso hoje — todo
tratamento de erro necessário é "mostrar a mensagem, ponto". Adicionar um
catálogo de códigos de erro sem um consumidor real seria complexidade
carregada à toa, na contramão do resto deste projeto (ver
`docs/ARQUITETURA.md` do repo back, que já rejeita dependências e camadas
sem necessidade concreta). Se uma tela futura precisar reagir a um erro
específico (não só exibi-lo), esse é o momento de estender o envelope com
um campo `codigo`, não agora.

## Consequências

- Toda mudança é no backend (`main.py`, dois exception handlers novos); o
  frontend ganha um contrato único para consumir, documentado no ADR-02
  (camada de serviço) e na Parte 3 (tasklist).
- Os testes de API já existentes (`backend/tests/test_api.py`) que hoje
  fazem asserção sobre o formato de erro `422` (lista) precisam ser
  atualizados para o formato novo — listado na tasklist do backend.
- Mensagens de erro continuam em português, prontas para exibição direta —
  nenhuma tradução ou catálogo de mensagens é necessário no frontend.

## Alternativas consideradas

- **Deixar como está e tratar as duas formas no frontend.** Rejeitada:
  empurra a inconsistência do backend para dentro de cada tela que trata
  erro, meses depois de perceberem o problema quando um formulário mostrar
  `[object Object]` num toast.
- **RFC 7807 completo.** Rejeitada por ora, ver seção acima — reconsiderar
  se/quando uma tela precisar de tratamento de erro programático, não só
  exibição.
