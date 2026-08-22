# ADR-0004 — Dois modos de ver o mesmo mês: planilha e painel

**Status:** implementado

## Contexto

O app nasceu como cópia fiel de uma planilha: doze páginas, uma por mês,
cada uma com containers em posições fixas. Essa forma é boa para lançar e
conferir — é a que a usuária já conhecia antes do app existir.

O pedido novo é outro: poder **arrumar a tela**, escolhendo quais blocos
aparecem e onde. Não é uma insatisfação com a planilha; é uma segunda
maneira de olhar os mesmos números, mais parecida com um painel.

A tentação é transformar a planilha na versão arrastável e acabar com a
distinção. Isso trocaria uma tela previsível por uma que a usuária precisa
manter arrumada — e num celular, onde ela mais usa o app, arrastar bloco é
desconfortável.

## Decisão

Existem **dois modos**, sobre os mesmos dados e as mesmas operações:

- `planilha` — a tela atual, containers fixos. Continua sendo o padrão.
- `estatico` (rotulado **Painel** na interface) — grade de blocos que a
  usuária arruma.

Nenhum dos dois é "o certo": são leituras diferentes do mesmo mês. Trocar
de modo não muda nada nos dados, não perde o ano/mês selecionado, e as
operações de escrita (criar lançamento, pagar fatura, marcar gasto fixo)
funcionam igual nos dois.

Estruturalmente:

- `App.tsx` cuida de sessão, busca de dados e escolha de modo. Não desenha
  tela.
- `pages/ModoPlanilha.tsx` e `pages/ModoEstatico.tsx` recebem **o mesmo
  pacote de props** (`pages/tiposModo.ts::PropsModo`). Um tipo só,
  compartilhado, é o que garante que um modo não fique com menos poder que
  o outro sem o TypeScript reclamar.
- `components/Cabecalho.tsx` é a barra comum (ano, mês, modo, tema), com um
  espaço `acoes` que cada modo preenche com seus botões próprios.

A escolha do modo mora no `localStorage`, **não no servidor**: é preferência
de aparelho. Faz sentido abrir o painel no PC e a planilha no celular, e
uma preferência sincronizada obrigaria a trocar toda vez que mudasse de
aparelho.

## Por que "modo", e não uma página separada

Uma rota `/painel` separada exigiria roteador (o app não tem um), duplicaria
a busca de dados e faria o ano/mês selecionado se perder na navegação. Como
os dois modos mostram exatamente o mesmo mês, manter o estado acima deles e
trocar só o componente que desenha é mais simples e resolve a preservação de
contexto de graça.

## Consequências

- O corpo de `App.tsx` foi extraído para `ModoPlanilha.tsx` sem mudança de
  comportamento — passo separado, de propósito, para que a extração pudesse
  ser conferida sozinha antes de qualquer coisa nova entrar.
- Todo container reaproveitado pelos dois modos ganhou uma prop `preencher`,
  que faz o `Card` ocupar a altura da célula da grade em vez da altura do
  próprio conteúdo. No modo planilha nada muda (o padrão é `false`).
- O painel é carregado sob demanda (`React.lazy`): ele traz
  `react-grid-layout` e o Recharts, que juntos pesam mais que todo o resto
  do app. Quem abre na planilha, no celular, não paga por eles.

## Alternativas consideradas

- **Substituir a planilha pelo painel.** Rejeitada: tiraria a tela que já
  funciona e que é a melhor no celular, para resolver um pedido que era de
  acrescentar, não de trocar.
- **Guardar o modo escolhido no servidor**, junto com o layout. Rejeitada:
  o layout faz sentido sincronizado (é trabalho que a usuária teve); qual
  modo abrir depende do aparelho em que ela está.
