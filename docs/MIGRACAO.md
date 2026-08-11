# Da planilha para o aplicativo

Este documento descreve o formato da planilha de origem, como importá-la e os
problemas encontrados nela — que o aplicativo não reproduz.

## Formato esperado

Uma aba por mês, nomeada com o nome do mês em português (`ABRIL`, `MAIO`, …).
Cada aba contém uma **tabela nomeada do Excel** com, no mínimo, as colunas:

| Coluna | Obrigatória | Observação |
| --- | --- | --- |
| `VALOR` | sim | Número positivo |
| `TIPO` | sim | Ver mapeamento abaixo |
| `DATA` | sim | Sem data, assume o dia 1º do mês |
| `CATEGORIA` | não | Usada apenas em saídas |
| `OBSERVAÇÕES` | não | Vira a descrição do lançamento |

O importador localiza a tabela pelas **tabelas nomeadas** (ListObjects), não
varrendo células. Isso é essencial: em abas com vários blocos lado a lado
(totais, gastos fixos, wishlist), há mais de uma coluna chamada `VALOR`, e uma
varredura por nome pegaria a errada silenciosamente.

### Mapeamento de tipos

| Planilha | Aplicativo |
| --- | --- |
| `Recebido` | `entrada` |
| `Gasto` | `saida` |
| `Guardado` | `guardado` |
| `Retirado` | `retirado` |
| `Rendimentos C` | `rendimento` (destino: conta) |
| `Rendimentos G` | `rendimento` (destino: guardado) |
| `Rendimentos` | `rendimento` (destino: guardado) — ver nota |

**Nota:** `Rendimentos` sem sufixo aparecia apenas nos primeiros meses, antes de
a distinção existir. É tratado como rendimento da reserva.

## Como importar

Sempre comece simulando:

```bash
cd backend
python -m scripts.importar_planilha "Planejamento.xlsx" --ano 2026 --simular
```

A saída lista quantos lançamentos cada aba produziria e **toda linha ignorada,
com o motivo**. Uma importação limpa não ignora nada; se ignorar, investigue
antes de gravar — cada linha descartada é dinheiro que some do histórico.

Confirmado o resultado, rode sem `--simular`, informando os saldos que existiam
antes do primeiro lançamento:

```bash
python -m scripts.importar_planilha "Planejamento.xlsx" --ano 2026 \
  --saldo-conta 0.97 --saldo-guardado 7867.36
```

O script se recusa a importar sobre um ano que já tenha lançamentos, para não
duplicar o histórico.

### Como conferir se deu certo

Compare o saldo de fechamento de cada mês calculado pelo aplicativo com o saldo
de abertura que estava digitado na aba seguinte da planilha. Eles devem
coincidir. Divergência aponta um lançamento faltando ou um ajuste manual que
nunca virou lançamento.

## Problemas encontrados na planilha de origem

Os itens abaixo foram identificados na planilha real que originou este projeto.
O aplicativo não reproduz nenhum deles; o script `corrigir_planilha.py` os
conserta em uma cópia, para quem quiser continuar usando o Excel na transição.

### 1. Referência cruzada errada no total guardado

A linha de agosto do container *Total guardado* somava `JUNHO[VALOR]` em vez de
`AGOSTO[VALOR]` — erro de copiar/colar replicado em todas as abas. Só não
aparecia porque agosto ainda não tinha valores guardados.

### 2. Rendimentos nunca entravam no total guardado

A fórmula usava `SUMIF(...; "Rendimentos"; ...)`, mas esse rótulo não existe nos
dados: os valores reais são `Rendimentos C` e `Rendimentos G`. O `SUMIF`
retornava zero em **todas** as abas, então nenhum rendimento jamais foi somado
à reserva.

### 3. A mesma pergunta dava respostas diferentes

A fórmula do total guardado da aba de abril não incluía as parcelas de
`Rendimentos G`, enquanto as outras oito abas incluíam. O total exibido mudava
conforme a aba aberta.

### 4. Rendimento da conta fora do saldo

`Rendimentos C` só entrava no *Total saldo* em três das nove abas.

### 5. Saldos de abertura digitados à mão

Cada aba trazia o saldo de abertura como número fixo na fórmula (`=0.97+…`,
`=39.78+…`). Duas consequências: corrigir um lançamento antigo não se propagava
para os meses seguintes, e as abas criadas e não usadas ficaram todas com o
valor de abril.

### 6. Título incorreto

As abas de julho a dezembro exibiam "TOTAL DE MAIO".

### 7. Fórmula órfã

`JUNHO!E9` repetia a fórmula de `E8` em uma linha sem rótulo.

## Gerando a planilha corrigida

```bash
cd backend
python -m scripts.corrigir_planilha "Planejamento.xlsx"
```

Gera `Planejamento - corrigida.xlsx` ao lado do original, que **não é
modificado**. Além de consertar os sete itens, o script encadeia os saldos: cada
mês passa a referenciar o fechamento do anterior (`=MAIO!E8+…`) em vez de um
número fixo.

**Atenção:** a biblioteca usada (openpyxl) reescreve o arquivo e pode descartar
gráficos e imagens. Abra a cópia e confira antes de descartar o original.
