# ADR-12 — Importação de extrato em PDF

**Status:** aceito — implementado no backend em 17/09/2026.

## Contexto

O `ADR-08` fechou a importação em OFX, CSV e XLSX. A Kamilly pediu PDF
também, e o motivo é concreto: o banco que ela mais usa, o Mercado Pago, não
oferece CSV — o extrato vem em PDF. Numa tentativa anterior ela converteu um
PDF para CSV por ferramenta externa, e o resultado chegou embaralhado, com
data, descrição e valor fundidos numa célula só.

Ler o PDF direto tira o conversor da equação.

## Decisão

### PDF entra como quarto formato, sem rota nova

`formato` aceita `"pdf"`, e `ler_pdf` entra no mesmo mapa de leitores que
`ler_ofx`, `ler_csv` e `ler_xlsx` já ocupam. Nada mais muda: os schemas, a
deduplicação, a sugestão de categoria e o fluxo de duas etapas continuam
iguais.

### `pypdf`, não `pdfplumber`

`pypdf` é wheel pura, 395 KB, sem dependência nenhuma. `pdfplumber` daria a
posição de cada palavra na página — melhor para reconhecer tabela — mas traria
`cryptography`, `pillow`, `cffi` e `pypdfium2` junto: dezenas de megabytes de
código binário num contêiner que hoje não tem nada disso, e uma aposta a mais
de ter wheel para CPython 3.14 (a restrição que já está anotada no
`requirements.txt`).

Com `pypdf` sobra o texto e a ordem das linhas. É menos do que as coordenadas
dariam, mas é o mesmo material com que o leitor de OFX já trabalha — lá também
se optou por expressão regular em vez de parser formal, e pelo mesmo motivo: o
que existe de fato é texto.

### Um perfil por banco, e recusa explícita para o resto

A primeira implementação tentou um padrão único e genérico: linha que começa
com data e termina com valor. Os dois extratos reais da Kamilly reprovaram a
ideia, cada um de um jeito diferente, e a lição foi a mesma — **não existe
layout genérico de extrato em PDF.**

**Mercado Pago**, `EXTRATO DE CONTA`:

```
Data Descrição ID da operação Valor Saldo
03-08-2026 Dinheiro retirado controle 171937846478 R$ 250,97 R$ 250,97
```

Cada linha traz **dois** valores: o da transação e o saldo corrente. O leitor
genérico pegava o último — importaria o saldo no lugar do lançamento, com
número plausível e errado. E a linha quebra: a data às vezes fica sozinha, com
a descrição continuando na seguinte.

**Nubank**, extrato da conta:

```
08 AGO 2026 Total de entradas + 941,55
Transferência recebida pelo Pix Kamilly da Rosa - MERCADO PAGO
IP LTDA. (0323) Agência: 1 Conta: 4100275488-6
941,55
```

A data é `08 AGO 2026`, com mês por extenso. O **sentido** do dinheiro não está
na linha da transação — está no cabeçalho do dia (`Total de entradas +`), e o
valor da transação vem sem sinal nenhum. A descrição atravessa duas linhas e o
valor fica numa terceira.

Nada disso se resolve com um regex de uma linha. Por isso há um leitor por
banco, escolhido por assinatura no texto, e **um erro claro quando nenhum
reconhece o arquivo**. Recusar o desconhecido é deliberado: um leitor genérico
erraria calado no Mercado Pago, e um número errado que parece certo é pior do
que uma recusa.

### Exigir centavos no valor

O padrão de valor pede `,dd` obrigatoriamente. Sem isso,
`Conta: 4100275488-6` e `CNPJ: 30.680.829/0001-43` viram valores, e o extrato
ganha lançamentos que nunca existiram.

### Linha não reconhecida é ignorada em silêncio

**Isto inverte a regra do `ADR-08`**, que mandava o leitor de planilha reclamar
alto de qualquer linha ilegível. A inversão é deliberada:

- numa planilha, **toda** linha abaixo do cabeçalho deveria ser transação;
- num PDF, a **maior parte** do texto nunca foi — cabeçalho, endereço, aviso
  legal, telefone da ouvidoria.

Reclamar de cada linha não reconhecida tornaria a importação inutilizável. A
proteção continua existindo, só que no fluxo: a prévia mostra `total_lidas` e
nada é gravado até a confirmação.

O que o leitor **recusa alto** é não ter entendido nada: PDF sem texto
(escaneado), layout desconhecido, ou perfil reconhecido sem nenhum lançamento.

### O identificador do Mercado Pago é da operação, não da transação

O extrato do Mercado Pago traz um `ID da operação` por linha, e usá-lo é
necessário: o extrato de agosto tem **dois** `Pix enviado Jose Vieira da Silva`
de R$ 89,00 no mesmo dia, operações diferentes que o identificador sintético
(data + valor + descrição) juntaria numa só.

Mas o ID sozinho não serve: um Pix e o **estorno** dele carregam o mesmo
número. No mesmo extrato havia três pares assim, e usar o ID cru teria apagado
R$ 89,00 três vezes, em silêncio. O identificador final é `ID + valor com
sinal` — separa o par e mantém a exatidão.

Consequência aceita: **PDF e CSV do mesmo extrato não deduplicam entre si**,
porque usam identificadores de origens diferentes. Quem importar os dois não
fica sem aviso — a prévia marca as linhas como `possivel_repetido` (mesma data
e valor) e elas vêm desmarcadas.

### PDF protegido por senha vazia

O extrato do Mercado Pago vem marcado como encriptado, mas abre com senha
vazia: é proteção de permissões (impedir edição), não de leitura. O leitor
tenta a senha vazia antes de desistir. Sem isso, o arquivo dela seria recusado
com uma mensagem pedindo para "salvar uma cópia sem senha" que não faria
sentido nenhum.

### Fatura de cartão fica de fora

Faturas escrevem a data sem o ano (`26/07`). Inferir o ano joga lançamento para
o ano errado em silêncio. O que funciona é **extrato de conta** em PDF — que é
o que a Kamilly usa para o Mercado Pago de qualquer forma.

## Consequências

- Uma dependência nova (`pypdf`), pura e pequena. Nenhuma migração.
- `PreviaImportacao`, `ConfirmarImportacao` e `ResultadoImportacao` não mudam.
- O identificador de deduplicação depende do perfil: o do Mercado Pago usa o
  `ID da operação` somado ao valor assinado; o do Nubank, que não traz
  identificador no PDF, cai no sintético como CSV e XLSX.
- O leitor de valores monetários saiu de `tabular.py` para `extrato.py`
  (`para_decimal`), porque PDF e planilha esbarram exatamente nas mesmas
  variações. Duas cópias divergiriam.
- Frontend: uma opção a mais no seletor, e um aviso de que PDF só funciona
  para os bancos conhecidos.
- **Conferido contra os dois extratos reais de agosto de 2026**, somando o que
  foi lido e comparando com os totais que os próprios documentos declaram:

  | | Transações | Entradas | Saídas |
  | --- | --- | --- | --- |
  | Nubank | 3 | R$ 941,56 ✓ | R$ 941,52 ✓ |
  | Mercado Pago | 61 | R$ 3.199,44 ✓ | R$ 3.169,68 ✓ |

  Os arquivos não entram no repositório — são dados financeiros dela. As
  fixturas dos testes reproduzem o **texto** que esses PDFs produzem.

## Alternativas consideradas

- **`pdfplumber` com extração de tabela** — descartada pelo peso das
  dependências binárias. O texto puro deu conta dos dois extratos reais, então
  a troca não se justificou.
- **Um leitor genérico, sem perfis** — foi a primeira implementação, e os
  arquivos reais a reprovaram. Mantê-la como último recurso para bancos
  desconhecidos foi cogitado e descartado: ela erraria calada justamente onde
  há duas colunas de valor, que é o caso do banco principal dela.
- **OCR para PDF escaneado** — fora de escopo. Traria Tesseract ou um serviço
  externo, e um extrato escaneado é raro quando o banco oferece OFX.
- **Continuar convertendo PDF para CSV por fora** — foi o que ela tentou, e o
  resultado dependia do conversor usado. Ler o PDF direto remove essa variável.
- **Inferir o ano de datas `DD/MM`** — adiada; ver acima.
