# ADR-0006 — O layout customizado é salvo em dois lugares: local, na hora, e no servidor, sob ação explícita

**Status:** proposto

## Contexto

Depois do ADR-0005, arrastar e redimensionar um widget já funciona na
tela — mas some ao recarregar a página se nada for guardado. É preciso
decidir **onde** esse arranjo fica: só no navegador (como o tema, ver
ADR-0004) ou também no servidor.

Diferente da preferência de modo (um clique para reconstituir) ou do tema
(idem), um layout customizado pode representar vários minutos de trabalho
manual — mover e redimensionar cada bloco até ficar do jeito que a pessoa
quer. Perder isso ao limpar os dados do navegador, trocar de aparelho ou
usar uma aba anônima é um custo bem maior do que perder a escolha de tema
claro/escuro.

## Decisão

**Local, imediato:** cada solta de arrasto ou redimensionamento grava o
layout inteiro no `localStorage` (chave `planejamento:layout-dashboard`),
na hora — sem round-trip de rede. É o que faz a interação parecer
instantânea e sobreviver a um F5 mesmo sem internet.

**Servidor, sob ação explícita:** um botão "Salvar layout" (visível só no
modo de edição — ver spec) envia o layout atual para o backend. Novo campo
`layout_dashboard: Mapped[str | None]` (JSON serializado como texto) em
`Usuario`, e dois endpoints:

- `GET /preferencias/layout-dashboard` — devolve o layout salvo, ou `null`
  se o usuário nunca salvou um.
- `PUT /preferencias/layout-dashboard` — substitui o layout salvo.

Registrados como os demais routers, em `main.py` — herdam a exigência de
sessão automaticamente (mesma dependência aplicada a todas as rotas, ver
`docs/ARQUITETURA.md`, "Como funciona a autenticação").

Ao abrir o modo painel: se existir layout no servidor, ele é a fonte da
verdade e sobrescreve o que está no `localStorage` daquele navegador
(cobre o caso de ter customizado em outro aparelho); se não existir nem no
servidor nem no local, usa o layout padrão de fábrica.

## Por que não salvar no servidor a cada arrasto

Um layout com 10 widgets sendo redimensionado gera dezenas de eventos de
mudança por segundo enquanto a pessoa está ajustando. Mandar uma
requisição HTTP a cada um deles seria, na prática, uma escrita contínua no
banco por causa de um gesto de mouse — sem nenhum ganho real, e com risco
de corrida entre abas (duas abas abertas, a última resposta a chegar
"vence", mesmo que não seja a mais recente da tela). O resto do app já
segue o padrão de "escrita é uma ação explícita, depois recarrega" (o
wrapper `acao()` em `App.tsx`) — o botão "Salvar layout" é a mesma ideia
aplicada aqui.

## Por que não só `localStorage`

O tema é reconstituído em um clique; um layout arrastado não. Perder um
layout customizado ao limpar os dados do navegador ou ao abrir o app em
outro computador é o tipo de frustração que desincentiva a pessoa a usar a
funcionalidade — o pedido do usuário foi explicitamente "deixar
totalmente customizável", o que implica que esse trabalho tem valor e
deveria durar. O custo de guardar (uma coluna de texto e dois endpoints
pequenos) é baixo perto disso.

## Consequências

- O `localStorage` vira um **cache local** do último estado, não a fonte
  de verdade — o servidor é. Isso evita duas fontes de verdade divergentes
  de forma permanente (o local é sempre reconciliado contra o servidor no
  carregamento).
- Precisa de uma migração Alembic (aditiva, coluna nullable) — mesma
  disciplina já estabelecida no projeto (ADR-0001 a 0003 da rodada
  anterior seguem o mesmo princípio).
- `layout_dashboard` guarda um JSON livre (lista de widgets + posição +
  tamanho + tipo). Não é validado item a item pelo Pydantic além de "é uma
  string" — o formato interno é responsabilidade do frontend, o backend só
  guarda e devolve. Isso é uma escolha deliberada de simplicidade: o
  schema de widgets muda mais rápido que o backend deveria precisar
  acompanhar (ex.: adicionar um tipo de widget novo não deveria exigir
  migração de banco).
- "Restaurar layout padrão" limpa as duas cópias (local e servidor) e
  recarrega o layout de fábrica.

## Alternativas consideradas

- **Só `localStorage`, sem backend.** Mais simples, zero mudança de
  schema — mas descarta o trabalho do usuário ao trocar de navegador ou
  limpar dados, o que contradiz o espírito de "customizável" do pedido.
  Rejeitada, mas registrada como a opção a cair de volta se, na prática,
  o usuário preferir simplicidade a durabilidade (é uma troca pequena de
  reverter).
- **Sincronização em tempo real (salvar a cada mudança, com debounce).**
  Mais "mágico", mas adiciona complexidade (debounce, cancelamento de
  requisição em voo, indicador de "salvando…") para resolver um problema —
  perder uma edição em andamento — que a cópia local já resolve sozinha
  entre um F5 e o próximo clique em "Salvar". Rejeitada por não valer o
  custo agora; pode ser revisitada se "esquecer de salvar" se mostrar um
  problema real de uso.
