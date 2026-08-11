# Arquitetura

Este documento registra as decisões técnicas do projeto e o motivo de cada uma.
A intenção é que quem voltar ao código daqui a um ano entenda *por que* está
assim, não só *como* está.

## Visão geral

```
┌──────────────────┐        HTTP/JSON       ┌──────────────────┐
│  React + TS      │ ─────────────────────► │  FastAPI         │
│  Tailwind        │ ◄───────────────────── │  (Python)        │
│  localhost:5173  │                        │  localhost:8000  │
└──────────────────┘                        └────────┬─────────┘
                                                     │ SQLAlchemy
                                                     ▼
                                            ┌──────────────────┐
                                            │  SQLite          │
                                            │  backend/dados.db│
                                            └──────────────────┘
```

Duas aplicações independentes que conversam por HTTP. O frontend não sabe nada
sobre o banco; o backend não serve HTML.

## Decisões

### Por que SQLite, e não Postgres

O projeto nasceu sem hospedagem definida. SQLite é um arquivo: não exige
servidor, instalação nem configuração, e o backup é copiar o `.db`.

A troca para Postgres é uma variável de ambiente:

```bash
DATABASE_URL=postgresql://usuario:senha@host/banco
```

Nenhum outro arquivo muda — o `database.py` já trata o parâmetro
`check_same_thread` como específico do SQLite. O que falta para produção é
substituir `Base.metadata.create_all()` por migrações (Alembic), necessário a
partir do momento em que houver dados que não se pode recriar.

### Por que `Decimal`, e não `float`

Dinheiro em ponto flutuante acumula erro: `0.1 + 0.2 != 0.3`. Somando centenas
de lançamentos, a diferença aparece nos centavos e o usuário perde a confiança
no total.

Consequências dessa escolha, que aparecem em todo o código:

- As colunas usam `Numeric(12, 2)`.
- Os cálculos em `services/calculos.py` convertem tudo para `Decimal` na
  entrada, com `str()` no meio (`Decimal(str(valor))`) — passar um `float`
  direto para `Decimal` carregaria o erro do float junto.
- A API serializa valores como **string** (`"1234.56"`), não como número. Se
  fossem números, o `JSON.parse` do navegador os converteria em float e o erro
  voltaria pela porta dos fundos.
- O frontend só converte para `Number` na hora de exibir, em `lib/formato.ts`.

Há um teste dedicado a isso: `test_centavos_nao_acumulam_erro`.

### Por que o cálculo é uma função pura

`services/calculos.py` recebe uma lista de lançamentos e devolve números. Não
abre sessão, não consulta o banco, não conhece HTTP.

Isso permite testar todas as regras de negócio com objetos simples, sem banco
nem servidor — a suíte de `test_calculos.py` roda em milissegundos e não tem
fixtures. Regras de dinheiro são exatamente o tipo de código que precisa ser
fácil de testar exaustivamente.

### Por que os saldos são encadeados

Na planilha original, o saldo de abertura de cada mês era um número digitado à
mão na aba correspondente. Isso criava dois problemas: corrigir um lançamento
antigo não se propagava, e meses novos ficavam com o valor desatualizado (de
setembro em diante, todos tinham o mesmo saldo de abril).

Aqui, `calcular_ano()` percorre os 12 meses em ordem e usa o fechamento de um
como abertura do próximo. Só existem dois números fixos no ano inteiro:
`saldo_inicial_conta` e `saldo_inicial_guardado`, no registro do ano.

Efeito colateral desejável: meses sem lançamento nenhum carregam o saldo
adiante em vez de zerar.

### Por que o mês é derivado da data

`Lancamento.mes` existe como coluna (para indexar e filtrar), mas nunca é
enviado pelo cliente — o router o calcula a partir de `data.month`. Se o
cliente pudesse mandar os dois, eles divergiriam, e um lançamento de 15 de
março apareceria na página de abril.

### Por que valores são sempre positivos

O sinal vem do `tipo`, nunca do número. Um sistema que aceita valores negativos
acaba com quatro maneiras de representar a mesma coisa (`-50` saída, `50`
saída, `-50` entrada...), e os totais passam a depender de qual convenção quem
digitou tinha em mente. A restrição está no banco (`CHECK valor > 0`) e no
schema (`Field(gt=0)`).

### Por que categorias são globais e não por ano

Comparar "quanto gastei com Comida em 2026 versus 2027" exige que seja a mesma
categoria. Se cada ano tivesse a sua, a comparação dependeria de casar nomes.

Por isso também categorias em uso não são apagadas, apenas desativadas
(`ativa = false`): remover uma categoria mudaria retroativamente os relatórios
de meses já fechados.

### Por que arquivar torna o ano somente-leitura

O arquivamento é o gesto de "fechar o livro". Se o ano arquivado continuasse
editável, o saldo de abertura do ano seguinte — copiado no momento do
arquivamento — silenciosamente deixaria de bater.

A dependência `obter_ano_editavel` bloqueia toda escrita em ano arquivado
(HTTP 409), enquanto `obter_ano` permite leitura normalmente.

### Por que não há biblioteca de estado no frontend

O aplicativo tem um único fluxo de dados: carrega o resumo do ano e os
lançamentos do mês, e recarrega após cada escrita. `useState` e `useEffect`
bastam. Introduzir React Query ou Redux aqui seria adicionar um conceito a mais
para quem for manter o código, sem resolver um problema que exista.

Se a aplicação passar a ter cache otimista, edição offline ou muitas telas
concorrentes, a decisão deve ser revista.

### Por que os tipos TypeScript são escritos à mão

`frontend/src/types/api.ts` espelha `backend/app/schemas.py` manualmente. Para
um projeto deste tamanho, gerar os tipos a partir do OpenAPI adicionaria uma
etapa de build e uma dependência para economizar poucas dezenas de linhas.

O risco é os dois arquivos divergirem — por isso ambos têm um comentário no
topo apontando um para o outro. Se o número de endpoints crescer muito, vale
migrar para geração automática (`openapi-typescript`).

## Caminho para produção

O que falta, na ordem em que deve ser feito:

1. **Autenticação.** Hoje a API é aberta. Enquanto roda em `localhost`, tudo
   bem; exposta na internet, não.
2. **Migrações** com Alembic, substituindo `create_all()`.
3. **Postgres**, via `DATABASE_URL`.
4. **CORS restrito** ao domínio real do frontend (hoje aceita `localhost:5173`).
5. **Deploy.** O frontend é estático (`npm run build` gera `dist/`) e pode ir
   para qualquer CDN; o backend precisa de um host com Python.
