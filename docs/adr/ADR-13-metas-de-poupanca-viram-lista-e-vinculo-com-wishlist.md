# ADR-13 — Metas de poupança viram lista (várias simultâneas) e podem vincular a um item da wishlist

**Status:** proposto

## Contexto

Hoje (ADR-06) só existe **uma** meta mensal e **uma** meta com prazo ativas
ao mesmo tempo, no sistema inteiro — `POST /metas-poupanca` aposenta
automaticamente a anterior do mesmo tipo (`criar()` em
`routers/metas_poupanca.py`). Isso fazia sentido quando "meta" era só um
hábito genérico ("guardar X por mês" / "juntar Y até uma data"), mas a
Kamilly quer algo mais específico: guardar dinheiro **para várias coisas ao
mesmo tempo** (ex.: um tênis, um curso), cada uma com o próprio progresso, e
ver esse progresso na Wishlist — não misturado num "total guardado" que soma
a reserva inteira.

A tela de Wishlist hoje (`wishlist.tsx`) mostra um card "Total guardado" que
é a soma do `guardado` de **todas** as contas correntes (via
`GET /anos/{ano}/resumo`), sem relação nenhuma com o que está de fato
reservado pra comprar os itens da lista — daí a reclamação "não deve ser o
total total guardado".

O sistema já tem um precedente **exato** pra "algo aponta pra uma meta
específica": `Caixinha.meta_id` (ADR-10) já deixa uma caixinha vinculada a
**uma** meta, e várias caixinhas podem apontar pra mesma meta. A wishlist
precisa do mesmo desenho: a `MetaPoupanca` aponta pra **um** item da
wishlist (não o contrário) — é a meta que "aponta pro objetivo", do mesmo
jeito que a caixinha aponta pra meta.

Perguntado explicitamente, a Kamilly confirmou que quer múltiplas metas
mensais **e** múltiplas metas com prazo simultâneas — não só liberar a meta
com prazo, como uma das opções apresentadas sugeria. Isso é uma mudança de
escopo maior do que "só adicionar um campo de vínculo", por isso vira ADR
próprio em vez de uma edição do ADR-06.

## Decisão

### `MetaPoupanca` ganha `nome` e `wishlist_item_id`, e perde o limite de "uma por tipo"

```python
class MetaPoupanca(Base):
    ...
    nome: Mapped[str | None] = mapped_column(String(60), nullable=True)
    wishlist_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("wishlist.id", ondelete="SET NULL"), nullable=True, index=True
    )
```

- `nome` é opcional — sem ele, a interface usa um rótulo genérico ("Meta
  mensal", "Meta com prazo até DD/MM"), igual mostra hoje. Só passa a
  importar diferenciar metas na lista quando há mais de uma do mesmo tipo;
  texto livre resolve isso sem forçar preenchimento de quem quer só uma
  meta simples, como é o uso de hoje.
- `wishlist_item_id` é **opcional** e a `MetaPoupanca` continua **global**
  (não pertence a um ano — ADR-06), mas o item que ela referencia pertence
  ao ano em que foi criado (`ItemWishlist.ano_id`). `ondelete=SET NULL`:
  apagar o item da wishlist não apaga a meta, só desfaz o vínculo — o
  dinheiro já guardado continua contando pra meta, só perde a etiqueta
  visual.
- **`POST /metas-poupanca` para de aposentar a meta anterior do mesmo
  tipo.** Isso reverte a parte do ADR-06 que dizia "no máximo uma ativa por
  tipo" — decisão explícita da Kamilly. O resto do ADR-06 (nunca apaga de
  verdade; `DELETE /metas-poupanca/{id}` desativa por id) continua igual —
  esse endpoint já opera por id específico, não precisa mudar.

### `GET /metas-poupanca/ativas` vira lista, não mais um par fixo

```ts
interface ProgressoMetaMensalOut {
  id: number;
  nome: string | null;
  wishlistItemId: number | null;
  valorAlvo: string;
  guardadoNoMes: string;
  percentual: number;
}
interface ProgressoMetaPrazoOut {
  id: number;
  nome: string | null;
  wishlistItemId: number | null;
  valorAlvo: string;
  dataAlvo: string;
  guardadoAcumulado: string;
  percentual: number;
  diasRestantes: number;
}
interface MetasAtivasOut {
  mensais: ProgressoMetaMensalOut[];   // era `mensal: ProgressoMetaMensalOut | null`
  prazos: ProgressoMetaPrazoOut[];     // era `prazo: ProgressoMetaPrazoOut | null`
}
```

A rota continua `GET /metas-poupanca/ativas` (mesmo caminho — só o corpo
muda de par-nulável pra duas listas; renomear o caminho por causa de uma
mudança de cardinalidade seria custo sem benefício). `_progresso_mensal`,
`_progresso_prazo` e `_caixinhas_da_meta` (em `metas_poupanca.py`) continuam
calculando o progresso de **uma** meta por vez, sem mudar a lógica interna —
o router só passa a iterar
`db.query(MetaPoupanca).filter(tipo=X, ativa=True).all()` em vez de
`.first()`.

### A wishlist não ganha endpoint novo — o vínculo é resolvido no frontend

`GET /anos/{ano}/wishlist` continua devolvendo `DesejoOut` sem nenhum campo
novo. A tela de Wishlist já vai precisar buscar `GET /metas-poupanca/ativas`
pra outros fins (mostrar quais metas existem); o vínculo item↔meta é um
filtro simples no cliente:

```ts
const metasDoItem = [...mensais, ...prazos].filter((m) => m.wishlistItemId === desejo.id);
```

Sem N+1, sem endpoint novo — as duas listas (desejos do ano, metas ativas)
já são buscadas inteiras pela tela.

### O que cada item da wishlist mostra quando tem meta vinculada

- Meta do tipo **prazo** vinculada: mostra `guardadoAcumulado / valorAlvo` e
  `percentual` — é o número que corresponde a "quanto já separei pra
  comprar isso".
- Meta do tipo **mensal** vinculada: mostra `guardadoNoMes / valorAlvo` com
  o rótulo "guardado este mês" — é uma medida diferente (fluxo do mês, não
  acumulado), e a interface não deve somar os dois tipos como se fossem a
  mesma coisa.
- Mais de uma meta pode apontar pro mesmo item (não há `UNIQUE` em
  `wishlist_item_id`, do mesmo jeito que várias caixinhas podem apontar pra
  mesma meta no ADR-10): a tela mostra todas, uma abaixo da outra — sem
  somar automaticamente, pela mesma razão do ponto anterior.

### O rodapé da Wishlist ganha um segundo número, sem substituir o primeiro

O card "Total guardado" (reserva geral, soma de todas as contas — sem
mudança nenhuma) continua como está. Um card novo, "Guardado nas metas
vinculadas", soma só `guardadoAcumulado` das metas **tipo prazo** vinculadas
a algum item **não comprado** do ano corrente — mesma razão do ponto
anterior: só o tipo prazo tem um número acumulado comparável a "dinheiro
guardado pra uma compra"; metas mensais vinculadas aparecem na exibição por
item (linha do item), mas não entram neste segundo total, pra não misturar
fluxo mensal com estoque acumulado.

## Consequências

- Migração: `metas_poupanca.nome` (`String(60)`, nullable) e
  `metas_poupanca.wishlist_item_id` (`Integer`, FK `wishlist.id`,
  `ON DELETE SET NULL`, nullable, indexado). Puramente aditiva.
- `MetaPoupancaCriar`/`MetaPoupancaAtualizar` ganham `nome?: string` e
  `wishlist_item_id?: number`. Se `wishlist_item_id` for informado, o
  backend valida que o item existe (mesmo padrão de `_validar_conta` usado
  em outros routers) — `422` se não existir.
- `MetaPoupancaSection.tsx` (usada em `/metas` e em Configurações → Perfil —
  o comentário do próprio arquivo já avisa "não duplicar a lógica em dois
  lugares", continua valendo) deixa de renderizar dois blocos fixos
  (`data?.mensal`, `data?.prazo`) e passa a mapear duas listas
  (`data.mensais.map(...)`, `data.prazos.map(...)`). O aviso "já existe uma
  meta ativa — criar substitui a anterior" sai do formulário, porque deixou
  de ser verdade.
- Formulário de nova meta ganha dois campos: "Nome (opcional)" e um
  `<select>` "Vincular a um item da wishlist (opcional)", populado com os
  itens não comprados do ano corrente (mesmo hook que a tela de Wishlist já
  usa).
- `test_perfil_metas_alertas.py`: os testes que hoje verificam "criar meta
  do mesmo tipo aposenta a anterior" mudam de expectativa — passam a
  verificar que as duas continuam ativas simultaneamente. Testes novos
  cobrem `wishlist_item_id` (criar com vínculo, `SET NULL` ao apagar o
  item, `422` com item inexistente).
- Nada muda em `Caixinha.meta_id` (ADR-10) — uma caixinha ainda vincula a
  uma meta específica por id; com várias metas do mesmo tipo possíveis
  agora, isso passa a ser mais útil (dá pra ter uma caixinha por meta), não
  menos.

## Alternativas consideradas

- **Vínculo no sentido contrário: `ItemWishlist.meta_id`.** Rejeitada
  porque inverte o precedente já estabelecido pelo ADR-10
  (`Caixinha.meta_id`, não `MetaPoupanca.caixinha_id`) sem motivo — nos
  dois casos é "a coisa mais específica aponta pra meta", não o contrário.
  Também exigiria decidir se um item pode ter só uma meta (mais restritivo
  do que a Kamilly pediu, já que ela não limitou isso).
- **Manter "uma meta ativa por tipo" e só permitir vincular a meta única
  existente a um item.** Foi uma das opções apresentadas à Kamilly; ela
  escolheu explicitamente permitir várias simultâneas — registrado aqui
  porque é uma mudança de escopo maior do que o pedido original descrevia,
  e vale ficar claro que foi decisão consciente, não deslize de escopo.
- **Endpoint novo, tipo `GET /anos/{ano}/wishlist/{id}/metas`.** Rejeitada —
  a lista de metas ativas já é pequena (uso individual) e a tela já precisa
  buscar todas as metas de qualquer forma; um endpoint por item geraria N
  chamadas onde uma já resolve.
