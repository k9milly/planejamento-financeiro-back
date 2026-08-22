# ADR-0007 — Widget é uma casca fina sobre os containers que já existem

**Status:** implementado

## Contexto

O painel precisa de blocos para mostrar. A pergunta é de onde eles vêm: se
são componentes novos, escritos para o painel, ou os mesmos containers que a
planilha já usa.

Escrever componentes novos é tentador — dá liberdade visual. Mas cada
número duplicado é uma segunda verdade sobre o mesmo dado: o dia em que a
regra de "quanto falta pagar" mudar, ela precisa mudar em dois lugares, e
um dos dois vai ficar para trás.

## Decisão

Um widget é uma **entrada no catálogo** (`components/widgets/catalogo.tsx`):
um nome para o menu, um tamanho inicial em unidades de grade, e uma função
que desenha. Quase toda entrada apenas monta um container que a planilha já
usa, com as mesmas props e os mesmos callbacks de escrita.

Dos onze blocos do catálogo v1, sete são reaproveitamento direto
(`TotaisMes`, `TotalGuardado`, `GastosPorCategoria`, `CalendarioVencimentos`,
`GastosFixos`, `Wishlist`, `TabelaLancamentos`) e quatro são novos, porque
não existiam em lugar nenhum: a rosca de categorias, as despesas diárias, a
abertura do mês e a fatura do cartão.

Consequência disso: **os widgets são operáveis**, não só informativos.
Marcar um gasto fixo como pago funciona dentro do painel, porque é o mesmo
componente com o mesmo callback. Um painel só de leitura obrigaria a voltar
para a planilha a cada ação.

### O catálogo é a única lista

O motor de grade, a persistência e o menu "+" leem `CATALOGO` — nenhum deles
sabe o que existe dentro de um widget. Acrescentar um bloco novo é
acrescentar uma entrada; o `IdWidget` é derivado das chaves, então um id
escrito errado no layout padrão não compila.

### O que entra no v1

Entra o que responde a uma pergunta que a usuária já fazia à planilha:
quanto tenho, quanto guardei, para onde foi, o que vence, quanto devo no
cartão, o que quero comprar. Fica de fora o que exigiria dado que a API não
tem (comparação entre meses, projeção) — não porque seja ruim, mas porque
inventar endpoint para encher o catálogo inverte a ordem certa das coisas.

Widgets calculados no cliente são permitidos quando o dado já está na tela:
"despesas diárias" deriva dos lançamentos do mês, que a página já buscou, e
não custa nenhuma chamada nova.

## Consequências

- Os containers reaproveitados ganharam a prop `preencher`, que faz o `Card`
  ocupar a altura da célula da grade e rolar o excesso. Sem ela, um card
  curto flutuaria no topo do bloco e um comprido vazaria por baixo.
- A moldura do bloco no painel **é** o próprio `Card` do container. Os
  controles de edição (punho de arraste e "✕") são sobrepostos por cima,
  para que nenhum widget precise saber que existe um modo de edição.
- Dois widgets mostram gastos por categoria — rosca e lista. Não é
  duplicação: a rosca responde "que fatia cada categoria levou", a lista
  responde "quanto foi em reais". A usuária escolhe qual quer, ou os dois.

## Alternativas consideradas

- **Widgets próprios, desenhados do zero.** Rejeitada: duplicaria a lógica
  de exibição de sete containers e criaria duas verdades para cada número.
- **Widgets só de leitura**, com as ações restritas à planilha. Rejeitada:
  faria o painel virar um relatório, e o pedido era ter a tela principal do
  jeito dela — não um segundo lugar para onde ir só para olhar.
