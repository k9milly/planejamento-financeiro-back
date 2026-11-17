# ADR-20 — Testes automatizados no frontend, começando pelo contrato com a API

**Status:** proposto

## Contexto

O frontend (`Planejamento-financeiro-frontend`) não tem nenhum teste
automatizado: o `package.json` só tem `dev`, `build`, `lint` e `format`. O
backend, ao contrário, tem uma suíte grande, com teste de regressão para quase
todo bug corrigido.

Em 13/11/2026 apareceu o custo disso. Desde o primeiro commit do frontend
(25/08), a busca da fatura do cartão chama

```
GET /anos/{ano}/cartoes/{cartao_id}/fatura?mes=11
```

mas a rota do backend, documentada na spec (seção 8) e no
`CONTRATO-API.md`, é

```
GET /anos/{ano}/cartoes/{cartao_id}/fatura/11
```

A chamada sempre respondeu `404`. Ninguém notou por quase três meses porque a
tela tinha um plano B silencioso: `fatura?.valorEmAberto ?? cartao.saldo`.
Quando a fatura não vinha, ela mostrava outro número, o saldo do cartão em
dezembro, que inclui todas as parcelas futuras do ano. Reproduzido rodando o
backend real: compra de R$ 60 em 2x, fatura de novembro correta no backend
(R$ 30), tela mostrando R$ 60. Depois de pagar, a situação nunca virava "paga"
na tela, o que levou a Kamilly a clicar em "Pagar" três vezes.

Dois aprendizados, e este ADR trata dos dois:

1. O backend estava certo e testado. O defeito estava na **fronteira** entre
   os repositórios, que nenhum dos dois testa.
2. O plano B silencioso transformou um erro visível (um `404`) num número
   errado e plausível, que é o pior tipo de bug num app de finanças.

## Decisão

### Vitest como ferramenta de teste

[Vitest](https://vitest.dev) é a ferramenta de teste feita para projetos
Vite, e este frontend já roda sobre Vite. Usa a mesma configuração e os
mesmos caminhos (`@/…`), sem uma segunda configuração para manter. Entram o
`vitest` e, para os testes de componente, `@testing-library/react` e `jsdom`.
O `package.json` ganha `"test": "vitest run"`.

**Cuidado específico deste repositório:** o `vite.config.ts` é gerenciado pelo
pacote da Lovable e avisa para não adicionar plugins (ver ADR-04). A
configuração do Vitest deve ficar num arquivo próprio (`vitest.config.ts`) que
reaproveita o que for preciso, em vez de editar o `vite.config.ts`. Se isso não
for possível sem mexer nele, parar e avisar a Kamilly antes.

### O primeiro teste é o do contrato

O teste que mais importa é o que teria pego este bug em agosto: **toda chamada
do `api-client.ts` precisa bater com uma rota que o backend realmente tem.**

O FastAPI já publica a lista exata das rotas em `/openapi.json`. O backend
passa a ter um script pequeno que exporta esse arquivo, e o frontend guarda uma
cópia dele (por exemplo em `src/lib/contrato/openapi.json`). O teste:

1. chama cada função do `api-client` com `requisitar` trocado por uma versão
   falsa, que só anota o método e a URL;
2. confere cada um contra os caminhos do `openapi.json`, tratando `{ano}`,
   `{mes}` e afins como "qualquer valor", e separando a query string do
   caminho.

A URL `/fatura?mes=11` falha nesse teste, porque `/fatura` não existe no
`openapi.json`. Quando o contrato mudar, o fluxo é: o back exporta o arquivo
de novo, a Kamilly copia para o front, e o teste mostra o que quebrou.

### Teste de regressão para cada bug corrigido nesta rodada

- A linha do cartão em Configurações e o card do Dashboard **não** mostram
  valor quando a fatura não carrega. Mostram estado de carregando ou de erro.
- A linha do cartão mostra "paga" quando a fatura volta com
  `situacao: "pago"`.
- O toast usa a duração certa por tipo (2,5 s sucesso, 5 s erro).

### Regra para o resto do código: sem plano B que troca o número

Quando um dado financeiro não carrega, a tela mostra que não carregou, nunca
outro número no lugar. O `??` com um valor de outra origem
(`fatura?.valorEmAberto ?? cartao.saldo`) é o padrão a evitar. Usar `?? 0`
como plano B tem o mesmo problema, porque "R$ 0,00 em aberto" é uma afirmação.

## Consequências

- Dependências novas de desenvolvimento no frontend (`vitest`,
  `@testing-library/react`, `jsdom`). Nenhuma vai para o build de produção.
- Script novo no backend para exportar o `openapi.json`, e uma cópia
  versionada dele no frontend que precisa ser atualizada quando o contrato
  muda.
- A suíte do frontend começa pequena, de propósito. A meta não é cobertura, é
  ter onde pôr o teste de regressão do próximo bug.
- Fica para depois rodar os testes no GitHub Actions a cada PR. O backend já
  usa o SonarQube; integrar o frontend é uma decisão separada.

## Alternativas consideradas

- **Testes ponta a ponta com Playwright**, abrindo o app de verdade contra um
  backend rodando. Pegariam este bug e outros mais, mas exigem os dois
  repositórios rodando juntos e são lentos e frágeis. É um bom segundo passo,
  não um primeiro.
- **Teste que só confere a URL escrita à mão no próprio teste**
  (`expect(url).toBe("/anos/2026/cartoes/1/fatura/11")`). Não pegaria este
  bug: quem escreveu a URL errada escreveria o teste com a mesma URL errada. O
  valor do teste de contrato é comparar com o que o backend publica, e não
  com o que o frontend acha.
- **Buscar o `openapi.json` do backend publicado durante o teste.** Evita
  manter a cópia, mas o teste passaria a depender de internet e do Fly estar
  acordado (o app hiberna). Uma cópia versionada é mais previsível.
