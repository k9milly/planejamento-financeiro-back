# ADR-19 — Parcela importada da fatura cai mês a mês, igual ao parcelamento manual

**Status:** proposto

**Revisa:** a regra de data das linhas "Parcela N de M" na seção "Fatura de
cartão do Mercado Pago (revisto em 04/11/2026)" do `ADR-12`. O resto daquela
seção continua valendo — inclusive a dedução do ano pela data de emissão.

## Contexto

O leitor de fatura do Mercado Pago (`services/pdf.py`, ADR-12) data cada linha
com a data impressa nela. Numa fatura de cartão, a linha de uma parcela traz a
data **da compra original**, repetida em toda fatura até a última parcela. Por
isso uma "Parcela 3 de 4" cobrada na fatura de outubro, de uma compra de
26/07, é importada como 26/07 — e há um teste garantindo isso
(`test_parcela_de_meses_atras_nao_e_jogada_para_a_frente`).

O teste protege a dedução do **ano** (um `26/07` numa fatura de outubro não
pode virar julho do ano seguinte), e isso continua certo. O problema é o
**mês**: importando as faturas de agosto, setembro, outubro e novembro, as
quatro parcelas terminam todas em 26/07. O gasto inteiro fica concentrado no
mês da compra, e os meses em que o dinheiro de fato sai do bolso ficam sem ele.

Isso contradiz o modelo que o próprio sistema já usa para parcelamento. O
`ADR-14` gera uma parcela por mês a partir da data da compra, de propósito
("uma parcela de cartão é dívida já assumida... uma parcela de março entra na
conta de março"). E contradiz o que a Kamilly descreveu como o comportamento
certo: uma compra de R$ 60 em 2x é R$ 30 neste mês e R$ 30 no seguinte.

Hoje os dois caminhos de registrar a mesma compra discordam:

| Caminho | "Parcela 2 de 2" de uma compra de 13/11 |
| --- | --- |
| Botão Parcelar (ADR-14) | 13/12 |
| Importar a fatura de dezembro (ADR-12) | 13/11 |

## Decisão

Linha de fatura com `Parcela N de M` na descrição recebe a data:

```
data da compra (com o ano deduzido pela regra atual do ADR-12) + (N − 1) meses
```

com dia inexistente no mês de destino caindo no último dia dele. É exatamente
a regra de `_datas_das_parcelas` em `routers/compras_parceladas.py`. A função
deve ser **movida para um módulo compartilhado** (por exemplo
`services/parcelas.py`) e usada pelos dois lugares, para que o parcelamento
manual e o importado nunca voltem a divergir por terem duas implementações.

Linha sem "Parcela N de M" não muda nada.

O leitor também passa a preencher `Lancamento.numero_parcela` com o `N` lido
da descrição (o campo já existe desde o ADR-14). A importação continua **não**
criando `CompraParcelada`, pelos motivos que o ADR-12 já registra.

### O identificador da linha não pode mudar

A chave de deduplicação da fatura é `fatura|data|descrição` (ADR-12). Se a
data usada na chave passar a ser a data deslocada, uma fatura já importada
antes desta mudança, se importada de novo, geraria chaves diferentes e
duplicaria tudo. A chave deve continuar sendo calculada a partir da data
**como impressa na linha**; só a data gravada no `Lancamento` muda.

### Consequência boa: os dois caminhos passam a se reconhecer

Com a mesma regra dos dois lados, a parcela importada nasce com a mesma data e
o mesmo valor da parcela que o botão Parcelar já tinha gerado. A prévia da
importação já marca como "parece o mesmo" o que tem data e valor iguais a um
lançamento existente (ADR-08), então quem parcelou à mão e depois importa a
fatura vê o aviso, em vez de ganhar a parcela em dobro sem perceber.

## Consequências

- `services/pdf.py`: ao montar a transação de uma linha de fatura, se a
  descrição tiver `Parcela N de M`, desloca a data em `N − 1` meses e preenche
  o número da parcela.
- `_datas_das_parcelas` sai de `routers/compras_parceladas.py` para um módulo
  de serviço compartilhado, sem mudar de comportamento.
- `test_parcela_de_meses_atras_nao_e_jogada_para_a_frente` muda de
  expectativa: a "Parcela 3 de 4" de 26/07 passa a ser 26/09. O que esse teste
  protegia (o ano não ir para a frente) continua coberto pelo
  `test_dezembro_numa_fatura_de_janeiro_volta_um_ano`, e vale acrescentar um
  caso de parcela que atravessa a virada de ano.
- Testes novos: reimportar a mesma fatura não duplica nada; a parcela
  importada é marcada como "parece o mesmo" quando a mesma compra já foi
  parcelada à mão; 31/01 com "Parcela 2 de 3" vai para o último dia de
  fevereiro.
- **Dados que já estão em produção:** a fatura de outubro de 2026 já foi
  importada com a regra antiga. As parcelas dela estão no mês da compra. Antes
  de corrigir qualquer coisa, levantar quantos lançamentos existem com
  "Parcela N de M" na descrição e `N > 1`, e propor à Kamilly um script de
  correção que rode primeiro em modo `--simular` (o mesmo padrão de
  `scripts/importar_planilha.py`). Nada de corrigir dado de produção sem ela
  ver a lista antes.

## Limitação que continua

O sistema não conhece o **dia de fechamento** do cartão (fora de escopo desde
o ADR-0003). Uma compra feita depois do fechamento entra, no banco, na fatura
do mês seguinte, e aqui a parcela 1 fica no mês da compra. A regra deste ADR
erra do mesmo jeito que o parcelamento manual, o que é melhor do que errar de
jeitos diferentes. Modelar o fechamento é uma extensão natural, e merece ADR
próprio quando for pedida.

## Alternativas consideradas

- **Manter a data da compra original.** É o "regime de competência": o gasto
  pertence ao mês em que foi decidido. É uma visão legítima, mas não é a que o
  resto do sistema usa (ADR-14) nem a que a Kamilly descreveu. Ter as duas ao
  mesmo tempo é o pior caso.
- **Usar a data de emissão da fatura para toda parcela.** Coloca a parcela no
  mês certo da fatura, mas com um dia que não é o da compra, e nunca bate com
  a data que o botão Parcelar gera. O aviso de "parece o mesmo" não
  funcionaria.
- **Criar a `CompraParcelada` completa a partir da linha importada.** Já
  rejeitado no ADR-12 e continua rejeitado: inventar as parcelas passadas e
  futuras a partir de uma linha solta erraria sem avisar.
