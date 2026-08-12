# Planejamento Financeiro

Aplicação web de controle financeiro pessoal, organizada como uma planilha de
12 páginas — uma por mês do ano. Substitui uma planilha de Excel mantida à mão,
preservando a mesma forma de pensar as finanças, mas com os cálculos corrigidos
e automatizados.

**Stack:** Python (FastAPI) · SQLite · React · TypeScript · Tailwind CSS

---

## Sumário

- [O que o aplicativo faz](#o-que-o-aplicativo-faz)
- [Conceitos do domínio](#conceitos-do-domínio)
- [Começando](#começando)
- [Importar uma planilha existente](#importar-uma-planilha-existente)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Testes](#testes)
- [Documentação adicional](#documentação-adicional)

---

## O que o aplicativo faz

Cada mês é uma página com quatro blocos:

| Bloco | Conteúdo |
| --- | --- |
| **Total guardado** | Quanto foi para a reserva em cada mês, mais o total acumulado |
| **Total de {mês}** | Entradas, saídas, guardado no mês e saldo de fechamento |
| **Gastos por categoria** | Ranking das saídas do mês, com barra proporcional |
| **Gastos fixos** | Despesas recorrentes do mês, com marcação de pago/pendente |
| **Vencimentos** | Calendário do mês marcando o dia de cada gasto fixo |
| **Wishlist** | Desejos com soma dos marcados, comparada com a reserva |
| **{Mês}** | Todos os lançamentos: data, tipo, categoria, descrição e valor |

Marcar um gasto fixo como pago gera o lançamento de saída correspondente e
atualiza saldo e gastos por categoria na hora; desmarcar o remove.

A wishlist responde à pergunta que motiva a lista: somando os itens marcados,
diz se cabem no que está guardado ou quanto falta.

O calendário e a lista operam sobre o mesmo dado: marcar em um reflete no outro.

**Arquivamento de ano** — ao fechar um ano, ele fica somente-leitura e o ano
seguinte é preparado com os saldos de fechamento como abertura. Também dá para
criar o próximo ano antes de arquivar, para começar a planejar: ao arquivar, os
saldos de abertura dele são corrigidos automaticamente.

**Importação de extrato** — envie o arquivo OFX do banco e revise as transações
antes de gravar. Reimportar o mesmo extrato não duplica nada, e as categorias
que você ensina uma vez são aplicadas sozinhas nas próximas importações. Veja
[`docs/MIGRACAO.md`](docs/MIGRACAO.md#extrato-bancário-ofx).

**Tema claro e escuro** — alternado no botão do cabeçalho. A escolha fica salva
no navegador; sem escolha anterior, segue a preferência do sistema.

## Conceitos do domínio

O sistema trabalha com **duas carteiras**: a *conta* (dinheiro do dia a dia) e o
*guardado* (a reserva). Cada lançamento tem um tipo que define como o dinheiro
se move entre elas:

| Tipo | Conta | Guardado | Quando usar |
| --- | --- | --- | --- |
| `entrada` | `+` | — | Recebi dinheiro (salário, presente) |
| `saida` | `−` | — | Gastei da conta |
| `guardado` | `−` | `+` | Movi da conta para a reserva |
| `retirado` | `+` | `−` | Tirei da reserva |
| `rendimento` | `+` ou — | — ou `+` | Rendeu; o campo `destino` diz onde |

Duas regras que o modelo garante:

1. **O valor é sempre positivo.** O sinal vem do tipo, nunca do número. Isso
   elimina a ambiguidade de "−50 do tipo saída".
2. **Só saídas têm categoria.** O relatório por categoria mede consumo; incluir
   transferências entre carteiras inflaria os números.

Os saldos são **encadeados**: o fechamento de um mês é a abertura do seguinte.
Corrigir um lançamento de abril se propaga por todos os meses seguintes
sozinho.

## Começando

**Pré-requisitos:** Python 3.11+ e Node.js 18+.

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

A API sobe em `http://localhost:8000`. A documentação interativa (Swagger) fica
em `http://localhost:8000/docs`.

### Frontend

Em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

A interface abre em `http://localhost:5173`.

### Primeiro usuário

Toda rota de dados exige sessão. Crie seu usuário antes de abrir a interface:

```bash
cd backend
python -m scripts.criar_usuario
```

A senha é pedida de forma interativa e não aparece na tela nem no histórico do
terminal. Rodar de novo com o mesmo e-mail troca a senha.

### Primeiro ano

Com a API rodando, crie o ano inicial:

```bash
curl -X POST http://localhost:8000/anos -H "Content-Type: application/json" -d "{\"ano\": 2026}"
```

Ou use o botão **Try it out** em `http://localhost:8000/docs`.

## Importar uma planilha existente

Se você já mantém uma planilha no formato descrito em
[`docs/MIGRACAO.md`](docs/MIGRACAO.md), o histórico pode ser importado de uma vez:

```bash
cd backend
python -m scripts.importar_planilha "caminho/Planejamento.xlsx" --ano 2026 --simular
```

O `--simular` mostra o que seria importado sem gravar nada. Confira o resultado
e rode de novo sem a flag, informando os saldos de abertura:

```bash
python -m scripts.importar_planilha "caminho/Planejamento.xlsx" --ano 2026 --saldo-conta 0.97 --saldo-guardado 7867.36
```

Há também um script que gera uma cópia corrigida da planilha original, para
quem quiser continuar usando o Excel durante a transição:

```bash
python -m scripts.corrigir_planilha "caminho/Planejamento.xlsx"
```

Os problemas que ele corrige estão listados em
[`docs/MIGRACAO.md`](docs/MIGRACAO.md).

## Estrutura do projeto

```
backend/
  app/
    main.py            Aplicação FastAPI e registro dos routers
    models.py          Modelos ORM (o domínio)
    schemas.py         Contratos de entrada e saída da API
    database.py        Conexão e sessão
    config.py          Configuração via variáveis de ambiente
    deps.py            Dependências compartilhadas
    routers/           Um arquivo por recurso
    services/
      calculos.py      Regras de totalização (puras, sem banco)
  scripts/
    importar_planilha.py   Importa o .xlsx para o banco
    corrigir_planilha.py   Gera cópia corrigida do .xlsx
  tests/               Testes de regras e de API

frontend/
  src/
    App.tsx            Layout, navegação entre meses e estado da página
    components/        Um componente por container da tela
    lib/api.ts         Cliente HTTP
    lib/formato.ts     Formatação em pt-BR
    types/api.ts       Tipos espelhando os schemas do backend
```

## Testes

```bash
cd backend
python -m pytest
```

A suíte cobre as regras de cálculo isoladamente (incluindo precisão decimal) e
o comportamento da API de ponta a ponta contra um banco temporário.

Verificação de tipos do frontend:

```bash
cd frontend
npm run lint
```

## Documentação adicional

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — decisões técnicas e o porquê delas
- [`docs/REGRAS.md`](docs/REGRAS.md) — regras de negócio em detalhe
- [`docs/API.md`](docs/API.md) — referência dos endpoints
- [`docs/MIGRACAO.md`](docs/MIGRACAO.md) — da planilha para o aplicativo

## Licença

[MIT](LICENSE).
