# ADR-0006 — Layout do painel é preferência por usuário, guardada como texto opaco

**Status:** implementado

## Contexto

O arranjo de blocos do painel (ADR-0004, ADR-0005) é trabalho que a usuária
teve: mover, redimensionar, escolher o que aparece. Precisa sobreviver a um
F5, e ela espera reencontrá-lo no outro aparelho.

Duas perguntas: **onde** guardar, e **quem entende** o formato.

## Decisão

### Onde: no servidor, por usuário — com cópia local

Coluna `usuarios.layout_dashboard` (texto, nullable) e dois endpoints,
`GET`/`PUT /preferencias/layout-dashboard`.

**Por usuário**, e não global: a disposição da tela é de quem a arrumou.
Isso o diferencia das cores da forma de pagamento, que são globais porque
são um vocabulário do app inteiro, não uma escolha de arrumação.

O `PUT` responde com o valor salvo em vez de `204`: mantém o mesmo formato
do `GET`, então o frontend usa a resposta direto como novo estado, sem uma
segunda chamada para reler.

Há também uma **cópia em `localStorage`**, gravada a cada mudança. Ela não
substitui o servidor — serve para a tela abrir já arrumada sem esperar a
resposta da rede, e para o arranjo não se perder se o `PUT` falhar. A ordem
de carregamento é **servidor → cópia local → padrão de fábrica**.

### Quem entende o formato: só o frontend

O campo `layout` é uma **string opaca** para o backend: ele guarda e devolve
sem olhar dentro. Validar o JSON no servidor obrigaria a mexer no backend a
cada bloco novo da interface — o formato é uma decisão de quem desenha a
tela, não do domínio financeiro.

A contrapartida é que **quem valida é o frontend, na leitura**
(`lib/layoutDashboard.ts::interpretar`): um JSON corrompido, de uma versão
antiga, ou citando um widget que não existe mais não pode derrubar a tela.
Item inválido é descartado; se sobrar nenhum, cai no padrão de fábrica.

### Quando salvar

Explicitamente, no botão "Salvar layout" — não a cada arraste. Salvar
sozinho encheria o servidor de escritas durante o ajuste e tiraria da
usuária a chance de experimentar e desistir. A cópia local, essa sim, é
gravada na hora: é barata e local.

"Restaurar padrão" volta ao layout de fábrica na tela e localmente, mas só
chega ao servidor quando ela salvar — pelo mesmo motivo.

## Consequências

- O backend não tem teste sobre o *conteúdo* do layout, só sobre guardar e
  devolver a string e sobre um usuário não ver o layout do outro.
- Widget removido do catálogo numa versão futura não quebra quem já tinha
  ele salvo: o item some do layout na primeira leitura, o resto sobrevive.
- Um layout salvo com todos os blocos removidos é lido como "nada salvo" e
  cai no padrão — mostrar uma tela vazia seria pior que mostrar o padrão.

## Alternativas consideradas

- **Só `localStorage`, sem servidor.** Rejeitada: perderia o arranjo ao
  trocar de aparelho ou limpar o navegador, e o pedido era justamente ter a
  tela do jeito dela.
- **Schema validado no backend** (tabela de blocos, com FK). Rejeitada:
  amarraria o servidor ao catálogo de widgets, fazendo toda mudança visual
  virar migração de banco.
- **Salvar a cada arraste.** Rejeitada: escritas demais e sem volta.
