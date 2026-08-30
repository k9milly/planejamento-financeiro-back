# ADR-08 — Importação de extrato bancário: CSV, XLSX e OFX

**Status:** aceito — implementado no backend em 30/08/2026.

## Contexto

A Kamilly quer importar extrato para já usar o site no dia a dia, e pediu
suporte a **CSV, XLSX e OFX** com um seletor de formato na tela, mais uma
tela de conferência manual para os casos incertos.

**Já existia** um subsistema de importação completo, testado e em produção —
só que limitado a OFX:

- `POST /anos/{ano}/importacao/ofx/previa` — lê o arquivo, **não grava nada**,
  devolve cada transação classificada.
- `POST /anos/{ano}/importacao/ofx/confirmar` — grava só o que foi
  aprovado/ajustado na prévia.
- Deduplicação por `fitid`, com identificador sintético (`data + valor +
  descrição`) quando o OFX não traz `FITID`.
- Três sinalizadores por linha: `duplicado`, `possivel_repetido`, `fora_do_ano`.
- Sugestão de categoria via `RegraCategorizacao`, aprendida no `aprender_padrao`.

O que não existia era o outro lado: **nenhum componente do frontend consome
nada disso** (confirmado por busca no repositório do front — zero ocorrências
de `importacao`/`ofx`), e o backend só lê OFX.

Por isso a decisão não é desenhar deduplicação do zero, e sim **generalizar o
que já existe e está testado**.

## Decisão

### 1. Formatos e rotas

As rotas deixam de ser específicas de OFX. Como nenhum consumidor existe, o
rename é seguro:

```
POST /anos/{ano}/importacao/previa
  multipart: arquivo (File) + formato ("csv" | "xlsx" | "ofx")
  → PreviaImportacao

POST /anos/{ano}/importacao/confirmar
  → ConfirmarImportacao → ResultadoImportacao
```

`formato` é **obrigatório**, não deduzido da extensão: a tela tem um seletor de
qualquer forma, e adivinhar formato daria um caminho a menos testado para
esconder um engano do usuário. Escolher `csv` e enviar um OFX responde `422`
com mensagem legível.

Os schemas de resposta (`PreviaImportacao`, `TransacaoPrevia`,
`ConfirmarImportacao`, `ResultadoImportacao`) **não mudaram** — ganharam só
mais duas origens de dado.

### 2. Parsers novos para CSV e XLSX

`ler_csv` e `ler_xlsx` vivem juntos em `app/services/tabular.py` (o que muda
entre eles é só como se chega às células; a interpretação de data, valor e
cabeçalho é a mesma), espelhando a assinatura de `ler_ofx`: bytes entram, lista
normalizada sai.

O tipo dessa lista virou `TransacaoExtrato`, em `app/services/extrato.py` —
antes chamava-se `TransacaoOFX` e morava no leitor de OFX. Do roteador para
dentro, nada sabe de qual formato a transação veio.

Layout aceito, já que nenhum banco tem um "CSV padrão": três colunas
identificadas **pelo nome do cabeçalho**, ordem livre, ignorando acentos e
maiúsculas — `data`, `valor`, `descricao`. `valor` com sinal, na convenção do
OFX (negativo = saída). Data em `AAAA-MM-DD` ou `DD/MM/AAAA`.

Além do mínimo acima, o parser tolera o que um arquivo real costuma trazer sem
que isso mude o layout combinado: linhas de preâmbulo antes do cabeçalho,
separador `;`, `,` ou tabulação, BOM do Excel, Latin-1, `R$`, separador de
milhar (`-1.234,56` e `-1,234.56` são o mesmo número) e linhas em branco.

Esse é um formato **da própria aplicação**, não o export nativo de um banco
específico. Se o arquivo real da Kamilly usar outros nomes de coluna, o ajuste
é mapear nomes dentro de `tabular.py` — nada fora dele sabe como o arquivo é
feito. **Isso ainda não foi conferido contra um arquivo real do banco dela.**

### 3. Erros são ruidosos na planilha, silenciosos no OFX

O leitor de OFX pula em silêncio uma transação sem data ou sem valor, porque
ali isso é anomalia de uma linha isolada. Na planilha, uma data ilegível quase
sempre significa que a **coluna inteira** está num formato não previsto —
descartar em silêncio importaria meio extrato sem ninguém perceber. Então
`ler_csv`/`ler_xlsx` levantam erro citando a linha do problema.

### 4. Deduplicação — reaproveitar, não recriar

CSV e XLSX nunca têm identificador de transação, então sempre caem no mesmo
identificador sintético que o backend já calcula e já testa para o OFX sem
`FITID`: `data + valor (com sinal) + descrição (até 40 caracteres)`.

O sinal faz parte da chave: sem ele, um Pix enviado e um recebido de mesmo dia
e mesmo montante colidiriam e o segundo sumiria como duplicata. Consequência
boa e testada: o **mesmo extrato baixado em CSV e em XLSX** gera os mesmos
identificadores, então importar os dois não duplica nada.

- `duplicado = true` → ignorado automaticamente na confirmação, sem perguntar.
- `possivel_repetido = true` (mesma data e valor, identificador diferente) → é
  o gatilho da tela de conferência manual.

Isso **revisa** o `backlog-refinado.md`, que sugeria hash de data + valor +
**conta**. A conta não faz parte da chave (ver ponto 5), e manter a estratégia
já testada evita duas lógicas de dedupe no mesmo sistema.

### 5. Conta é escolhida na confirmação, não no upload

O contrato já pede `conta_id` por transação em `POST .../confirmar`. A tela
pode simplificar para um seletor único no topo da prévia, aplicado a todas as
linhas ao montar o payload — sem mudança no backend.

### 6. Tela de importação (frontend, do zero)

Não existe nada hoje; é a maior parte do trabalho deste item. Ver seção 13 de
`docs/specs/especificacao-tecnica-funcional.md` para o contrato completo.

## Consequências

- Backend: dois parsers novos + um módulo de vocabulário comum + rename das
  duas rotas. **Nenhuma migração de banco** — `Lancamento.fitid` e
  `RegraCategorizacao` já sustentam os três formatos.
- Nenhuma dependência nova: `openpyxl` já estava no `requirements.txt` (usado
  pelos scripts de importação da planilha antiga) e o `csv` é da biblioteca
  padrão.
- Frontend: tela nova inteira, sem nada reaproveitável de tela anterior.
- Testes: 26 novos em `tests/test_tabular.py` (parsers) e 11 em
  `tests/test_importacao.py` (fluxo nos três formatos).

## Alternativas consideradas

- **Construir um subsistema novo, com dedupe por hash de data + valor +
  conta** — era a direção do backlog refinado; descartada ao encontrar a
  implementação de OFX pronta e testada. Reaproveitar é mais seguro do que
  manter duas lógicas de deduplicação.
- **Suportar só OFX por enquanto** — descartada; ela pediu os três formatos
  explicitamente, para importar independente do que o banco oferecer.
- **Deduzir o formato pela extensão do arquivo** — descartada; ver ponto 1.
- **Pedir a conta no upload, antes da prévia** — descartada; o contrato já
  resolve isso por transação na confirmação.
