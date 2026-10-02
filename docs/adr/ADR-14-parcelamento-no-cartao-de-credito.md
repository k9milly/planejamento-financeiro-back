# ADR-14 — Compra parcelada no cartão de crédito, com juros opcional

**Status:** proposto

## Contexto

Hoje uma compra no crédito (`ADR-0001`, `ADR-0002`) é sempre **um**
`Lancamento` do tipo `saida`, `forma_pagamento=credito`, datado no dia da
compra. Não existe nenhum conceito de parcelamento — `grep` por
"parcela"/"juros" no backend não retorna nada. A fatura de um cartão nunca é
armazenada: é sempre a soma dos lançamentos de crédito daquela conta até
agora (`ADR-0003`), e o sistema **decidiu conscientemente não modelar
fechamento de fatura** — só vencimento.

A Kamilly quer poder, ao lançar uma compra no crédito, dizer em quantas
vezes ela foi parcelada (com um campo numérico de subir/descer, não um
`<select>` com opções fixas), se tem juros, e — se tiver — informar o valor
dos juros do jeito que for mais conveniente na hora: digitando o valor de
cada parcela direto (como o próprio cartão já mostra, ex. "10x de
R$105,32") **ou** digitando uma taxa de juros ao mês, deixando o sistema
calcular.

## Decisão

### Cada parcela é um `Lancamento` normal — igual já funciona hoje

Nenhuma mudança em `services/calculos.py` ou em como a fatura é somada: uma
compra parcelada em N vezes gera **N lançamentos reais**, um por mês, cada
um com `forma_pagamento=credito` e `conta_id` do cartão — exatamente como um
lançamento manual futuro já se comporta hoje. Isso reaproveita 100% do
cálculo de fatura/saldo que já existe (mesmo raciocínio do ADR-0003: "não
guardar o que pode ser derivado"). O que falta é só **gerar as N linhas de
uma vez** e lembrar que elas pertencem à mesma compra, para mostrar "3/10" e
permitir apagar a série inteira se for o caso.

### `CompraParcelada` — o "molde", como `GastoFixo` é o molde do gasto fixo

```python
class ModoJuros(str, enum.Enum):
    VALOR = "valor"            # a pessoa digita o valor de cada parcela
    PERCENTUAL = "percentual"  # a pessoa digita uma taxa % ao mês

class CompraParcelada(Base):
    __tablename__ = "compras_parceladas"

    id: Mapped[int] = mapped_column(primary_key=True)
    descricao: Mapped[str] = mapped_column(String(120), nullable=False)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id", ondelete="SET NULL"))
    numero_parcelas: Mapped[int] = mapped_column(Integer, nullable=False)   # 2..24
    tem_juros: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    modo_juros: Mapped[ModoJuros | None] = mapped_column(Enum(ModoJuros, native_enum=False), nullable=True)
    taxa_juros_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)   # só modo=percentual
    valor_parcela: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)          # valor de cada parcela, já calculado
    valor_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)            # soma efetiva das parcelas
    criada_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("numero_parcelas BETWEEN 2 AND 24", name="ck_compra_parcelada_numero"),
    )
```

`Lancamento` ganha dois campos, só preenchidos quando ele nasce de uma
compra parcelada:

```python
compra_parcelada_id: Mapped[int | None] = mapped_column(
    ForeignKey("compras_parceladas.id", ondelete="CASCADE"), nullable=True, index=True
)
numero_parcela: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1-based: "3" de "3/10"
```

`ondelete=CASCADE`: apagar a `CompraParcelada` (ver endpoint abaixo) apaga
junto todas as parcelas que ainda existirem como lançamento — é a ação
"desfazer a compra inteira". Apagar **uma** parcela isolada continua sendo o
`DELETE /anos/{ano}/lancamentos/{id}` que já existe hoje, sem nenhuma regra
nova: a parcela é um lançamento como outro qualquer, editável e excluível
individualmente (ex.: a Kamilly corrige o valor de uma parcela específica
porque o extrato do banco veio diferente).

### Como o valor de cada parcela é calculado

Três combinações, todas resolvidas no backend (o frontend manda os dados
brutos que a pessoa digitou; quem calcula é o servidor, pra não ter duas
implementações do mesmo cálculo):

| `tem_juros` | `modo_juros` | O que a pessoa digita | Como o backend calcula |
| --- | --- | --- | --- |
| `false` | — | `valor_total` (valor da compra) | `valor_parcela = valor_total / numero_parcelas`, arredondado a 2 casas; a **última** parcela absorve a diferença de centavos (ex.: R$100 em 3x = R$33,33 + R$33,33 + R$33,34) |
| `true` | `valor` | `valor_parcela` (o que o cartão já mostra, ex. "10x de R$105,32") | `valor_total = valor_parcela × numero_parcelas` — nenhuma conta financeira, só multiplicação; todas as parcelas saem iguais |
| `true` | `percentual` | `valor_total` (preço à vista) + `taxa_juros_pct` (% ao mês) | Juros simples: `juros = valor_total × (taxa_juros_pct / 100) × numero_parcelas`; `valor_parcela = (valor_total + juros) / numero_parcelas`, arredondado, última parcela absorve o resto |

**Por que juros simples, e não a Tabela Price (juros compostos) que os
bancos usam de verdade:** a Tabela Price exige uma fórmula de amortização
mais complexa, e mesmo assim **não teria garantia de bater exatamente** com
o número que o banco da Kamilly calculou (cada banco pode arredondar e
compor de um jeito ligeiramente diferente) — então a precisão adicional não
compraria uma vantagem real. Juros simples é previsível, fácil de explicar
("guardei R$X de juros no total") e, para quem quer o número exato do
banco, o modo `valor` (digitar a parcela direto) já resolve sem nenhuma
aproximação. Documentado aqui para não ser lido como descuido depois.

### Onde as parcelas futuras "caem" — anos ainda não criados

`Ano` é criado manualmente (`POST /anos`) — uma compra parcelada em 12x
lançada em setembro/2026 tem parcelas caindo em 2027, ano que pode não
existir ainda no sistema. A criação da compra parcelada **cria
silenciosamente** os anos que faltarem (mesmo formato do `POST /anos`, sem
saldos iniciais informados — todos zero), pelo mesmo motivo do resto do
sistema: a parcela é uma dívida real e já assumida no ato da compra, não
algo que deveria ficar "perdido" à espera de a pessoa lembrar de criar o
ano seguinte.

Exceção: se o ano de destino já existir e estiver **arquivado**
(somente-leitura), a criação da compra parcelada inteira falha com `422`
("Não é possível parcelar até {ano}, que já está arquivado") — não tenta
desarquivar sozinho. Isso deveria ser raríssimo na prática (parcelas seguem
sempre pra frente a partir de hoje; um ano futuro já arquivado é uma
inconsistência que a pessoa criou por conta própria).

### Endpoint novo

```ts
interface CompraParceladaCriar {
  descricao: string;
  conta_id: number;
  categoria_id?: number;
  data_primeira_parcela: string;   // YYYY-MM-DD
  numero_parcelas: number;          // 2..24
  tem_juros: boolean;
  modo_juros?: "valor" | "percentual";     // obrigatório se tem_juros=true
  valor_total?: string;             // obrigatório se !tem_juros OU modo_juros="percentual"
  valor_parcela?: string;           // obrigatório se modo_juros="valor"
  taxa_juros_pct?: string;          // obrigatório se modo_juros="percentual"
}
interface CompraParceladaOut {
  id: number;
  descricao: string;
  numero_parcelas: number;
  tem_juros: boolean;
  modo_juros: "valor" | "percentual" | null;
  taxa_juros_pct: string | null;
  valor_parcela: string;
  valor_total: string;
  parcelas: LancamentoOut[];   // as N linhas já geradas
}
```

- `POST /anos/{ano}/compras-parceladas` — `{ano}` é o ano da primeira
  parcela (`obter_ano_editavel`, igual aos demais routers); cria o grupo e
  as N linhas de `Lancamento` de uma vez, uma por mês a partir de
  `data_primeira_parcela` (mesmo dia do mês seguinte; dia inexistente usa o
  último dia do mês, mesmo tratamento que `gastos_fixos.py` já faz com
  `calendar.monthrange`). `descricao` de cada parcela gerada:
  `"{descricao} ({i}/{numero_parcelas})"`.
- `DELETE /anos/{ano}/compras-parceladas/{id}` — apaga o grupo; o `CASCADE`
  remove todas as parcelas que ainda existirem como lançamento, em
  qualquer ano em que estejam. Usado quando a compra inteira é desfeita
  (devolução, quitação antecipada fora do fluxo normal).
- Validação de coerência reaproveitada: `conta_id` precisa ser
  `cartao_credito` (mesma regra da tabela do ADR-0002) — `422` se não for.

### Formulário de novo lançamento

Só aparece quando `forma_pagamento = crédito` está selecionado:

1. Alternador **"Parcelar"** (desligado por padrão — comportamento de hoje,
   um lançamento só).
2. Ligado, aparecem:
   - **Número de parcelas** — campo numérico com botões `−`/`+` visíveis
     (não depender das setinhas nativas de `<input type="number">`: no
     Safari/iOS elas não aparecem de jeito nenhum, e a Kamilly usa o app
     principalmente no celular — ver seção correspondente na spec).
     Mínimo 2, máximo 24.
   - **Tem juros?** — alternador Sim/Não (padrão Não).
   - Se **Não**: reaproveita o campo "Valor" já existente no formulário
     como o valor total da compra.
   - Se **Sim**: escolha "Como você quer informar":
     - **"Valor de cada parcela"** → um campo, "Valor de cada parcela
       (R$)".
     - **"Taxa de juros"** → dois campos, "Valor total (à vista) (R$)" e
       "Juros ao mês (%)".

## Consequências

- Migração: tabela `compras_parceladas` nova + `lancamentos.compra_parcelada_id`
  (FK, `ON DELETE CASCADE`, nullable, indexado) + `lancamentos.numero_parcela`
  (Integer, nullable). Puramente aditiva — lançamentos existentes nascem com
  os dois campos nulos e continuam se comportando exatamente como hoje.
- Nenhuma mudança em `services/calculos.py`: fatura, saldo e "quanto devo no
  cartão" continuam somando lançamentos normalmente — uma parcela futura só
  entra na conta do mês em que a própria `data` cair, igual qualquer
  lançamento datado no futuro já se comporta hoje.
- A tela de Lançamentos ganha uma coluna/badge "3/10" quando
  `numero_parcela`/`compra_parcelada_id` estiverem preenchidos, e uma ação
  "Excluir compra inteira" (chama o `DELETE` do grupo) ao lado da exclusão
  individual que já existe.
- Editar uma parcela isolada (`PATCH /anos/{ano}/lancamentos/{id}`) não tem
  regra nova — continua um lançamento comum. Isso significa que editar o
  valor de uma parcela **não** recalcula as outras nem o `valor_total` do
  grupo — é uma correção pontual daquele mês, não uma renegociação da
  compra inteira (se a pessoa quiser isso, apaga o grupo e lança de novo).
- Testes novos: cálculo dos três modos (sem juros, com juros por valor, com
  juros por percentual — incluindo arredondamento da última parcela),
  criação automática de ano faltante, `422` em ano de destino arquivado,
  `422` em conta que não é cartão, `CASCADE` ao apagar o grupo.

## Alternativas consideradas

- **Tabela Price (juros compostos), como os bancos calculam de verdade.**
  Rejeitada — ver justificativa na seção de cálculo acima: mais complexa e
  sem garantia de bater com o número real do banco, sem ganho prático sobre
  o modo "digitar a parcela direto" para quem quer precisão.
- **Gerar as parcelas sob demanda (uma por vez, tipo `GastoFixoMensal` com
  `pagar`/`desfazer`), em vez de todas de uma vez.** Rejeitada: uma parcela
  de cartão é uma dívida já assumida no momento da compra — diferente de um
  gasto fixo, que pode variar ou ser pulado mês a mês — então esconder as
  parcelas futuras até "confirmar" cada uma esconderia da Kamilly um
  compromisso que já existe, contrariando o "saldo inteligente" que motivou
  o ADR-0002.
- **Bloquear a criação se algum ano de destino não existir, em vez de
  criar sozinho.** Rejeitada por atrito sem benefício — a pessoa teria que
  sair do formulário, criar o ano manualmente, voltar; o ano criado
  automaticamente já nasce com o mesmo formato (zero saldos iniciais) que
  criar na mão produziria.
- **Limite de parcelas maior que 24 (ou sem limite).** Rejeitado por agora:
  24 já cobre o uso comum de cartão brasileiro; sem teto, um erro de
  digitação (ex. "240" em vez de "24") geraria 240 lançamentos e múltiplos
  anos criados por engano. Pode virar um valor maior se a necessidade real
  aparecer.
