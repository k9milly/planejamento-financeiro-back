# Importando dados

Duas origens: a planilha antiga (uma vez só, no começo) e o extrato do banco
(sempre que quiser lançar o mês).

## Extrato bancário (OFX, CSV ou XLSX)

Baixe o extrato pelo aplicativo do banco e use o botão *Importar extrato* no
cabeçalho, escolhendo o formato do arquivo. O fluxo tem duas etapas e **nada é
gravado na primeira**.

Prefira **OFX** quando o banco oferecer: só nele existe o identificador de
transação do próprio banco, que torna a deduplicação exata. CSV e XLSX
funcionam igual em todo o resto — a diferença está explicada em
*Deduplicação*, abaixo.

### Por que a revisão é obrigatória

O extrato diz quanto entrou e saiu, mas não diz o que aquilo significa. Um Pix
recebido pode ser salário ou a devolução de um amigo; uma transferência para a
poupança aparece como saída, mas é `guardado` — dinheiro que continua seu, só
trocou de carteira. Classificar isso sozinho produziria totais errados com cara
de certos, então a tela mostra a sugestão e quem decide é você.

### O que a prévia mostra

| Coluna | O que faz |
| --- | --- |
| Incluir | Marque o que vai virar lançamento |
| Tipo | Sugerido pelo sinal do valor; ajuste quando for transferência |
| Categoria | Preenchida por regra, quando houver; só vale para saídas |
| Lembrar | Cria uma regra para categorizar sozinho da próxima vez |

Linhas já importadas vêm bloqueadas e desmarcadas. Linhas de outro ano vêm
desmarcadas e sinalizadas. Uma linha com mesma data e mesmo valor de um
lançamento existente ganha um aviso — provavelmente você já digitou aquilo à
mão antes de importar.

### Deduplicação

Cada transação do OFX tem um `FITID`, o identificador que o banco dá a ela.
Ele é gravado junto com o lançamento, então **reimportar o mesmo extrato não
duplica nada**: as transações repetidas são reconhecidas e ignoradas. Extratos
com períodos sobrepostos são seguros.

Quando o banco não envia `FITID` — e sempre, em CSV e XLSX, onde esse campo
não existe —, o sistema deriva um identificador estável de data + valor +
descrição. Funciona, mas é menos confiável: duas compras idênticas no mesmo
dia, com a mesma descrição, seriam vistas como a mesma.

Como a regra é a mesma nos três formatos, baixar o **mesmo** extrato em CSV e
em XLSX e importar os dois não duplica nada.

### Regras de categorização

Uma regra é um trecho de texto e uma categoria: `IFOOD` → Comida. A comparação
ignora acentos e maiúsculas. Quando mais de uma regra casa, vence a de padrão
mais longo — `MERCADO LIVRE` ganha de `MERCADO`.

A sugestão nunca é aplicada sozinha: ela só preenche a tela de revisão.

### Bancos

O leitor aceita OFX 1.x (SGML, o formato que os bancos brasileiros usam) e
OFX 2.x (XML), em UTF-8 ou ISO-8859-1. Usa `MEMO` como descrição e cai para
`NAME` quando o banco preenche só esse.

### CSV e XLSX

Não existe "CSV padrão de banco" — cada um exporta o que quer. Então o formato
aceito aqui é o da própria aplicação: uma planilha com três colunas
identificadas **pelo nome do cabeçalho**, em qualquer ordem (acentos e
maiúsculas não importam):

| Coluna | O que vai nela |
| --- | --- |
| `data` | `AAAA-MM-DD` ou `DD/MM/AAAA` |
| `valor` | Com sinal: **negativo é saída**, positivo é entrada |
| `descricao` | O texto que aparece no extrato |

Linhas antes do cabeçalho, linhas em branco, `R$`, separador de milhar e
separador `;` ou `,` são tolerados. Linhas com valor zero são ignoradas.

Se uma data ou um valor não puder ser lido, a importação **para e diz em qual
linha** — numa planilha isso quase sempre significa que a coluna inteira está
num formato diferente, e importar metade em silêncio seria pior.

---

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

## Como importar os lançamentos

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

## Como importar os gastos fixos

A tabela `GastosFixos` da planilha entra por um script próprio:

```bash
python -m scripts.importar_gastos_fixos "Planejamento.xlsx" --ano 2026 --simular
```

Os gastos entram como **modelos pendentes em todos os meses**, mesmo os que a
planilha marca como "Pago". O motivo: os lançamentos daqueles pagamentos já
vieram na importação dos lançamentos, e marcá-los como pagos aqui criaria um
segundo lançamento para o mesmo dinheiro.

## Mudanças de schema

`create_all()` cria tabelas que faltam, mas nunca altera uma tabela existente.
Depois de atualizar o código, rode:

```bash
python -m scripts.migrar
```

É idempotente. Faça uma cópia do `dados.db` antes, por precaução.

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
