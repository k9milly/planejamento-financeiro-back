# Modo painel e catálogo de widgets

Spec da rodada que acrescentou o segundo modo de visualização e os blocos
ajustáveis. Decisões e seus porquês estão nos ADRs
[0004](../adr/0004-dois-modos-de-visualizacao.md),
[0005](../adr/0005-motor-de-grade.md),
[0006](../adr/0006-persistencia-do-layout.md) e
[0007](../adr/0007-escopo-do-catalogo-de-widgets.md); aqui está o detalhe do
que foi construído.

O que a API expõe está em [`../CONTRATO-API.md`](../CONTRATO-API.md). Esta
rodada usa dela apenas `GET`/`PUT /preferencias/layout-dashboard`; todo o
resto reaproveita endpoints que já existiam.

## 1. Os dois modos

| | `planilha` | `estatico` (rótulo: **Painel**) |
| --- | --- | --- |
| Arranjo | containers fixos | grade de 12 colunas, ajustável |
| Padrão | sim | — |
| Onde a escolha mora | `localStorage`, chave `planejamento:modo` | idem |
| Dados | os mesmos | os mesmos |
| Escrita | toda | toda |

Alternar preserva ano e mês: os dois vivem em `App.tsx`, acima dos modos.

Arquivos:

- `lib/modoVisual.ts` — `useModoVisual()`.
- `pages/tiposModo.ts` — `PropsModo`, o pacote que os dois modos recebem.
- `components/Cabecalho.tsx` — barra comum; cada modo passa suas `acoes`.
- `pages/ModoPlanilha.tsx` — extraído de `App.tsx` sem mudança de
  comportamento.
- `pages/ModoEstatico.tsx` — grade, modo de edição e persistência.

## 2. Carregamento e persistência

O layout é um `ItemLayout[]` serializado em JSON:

```ts
interface ItemLayout {
  i: IdWidget;  // chave no catálogo
  x: number; y: number; w: number; h: number;  // unidades de grade
}
```

Para o servidor isso é **texto opaco** — ele guarda e devolve sem validar
(ADR-0006). Quem valida é `lib/layoutDashboard.ts::interpretar`, na leitura.

Ordem de carregamento:

1. `GET /preferencias/layout-dashboard` — a verdade entre aparelhos.
2. `localStorage`, chave `planejamento:layout-painel` — cobre o intervalo
   até o servidor responder, e a rede caída.
3. `LAYOUT_PADRAO` — o padrão de fábrica.

Quando salva:

| Ação | `localStorage` | Servidor |
| --- | --- | --- |
| Arrastar / redimensionar | na hora | não |
| Adicionar / remover bloco | na hora | não |
| "Salvar layout" | na hora | `PUT` |
| "Restaurar padrão" | na hora | só ao salvar depois |

Só o layout da **tela larga** é gravado. O reflow para telas menores é
derivado, e persistir o derivado apagaria o arranjo de 12 colunas
(ADR-0005) — por isso o modo de edição também só aparece na tela larga.

## 3. Modo de edição

Ligado pelo botão "Editar layout". Enquanto ativo:

- cada bloco ganha uma faixa com o punho de arraste (`.puxador`) e um "✕"
  para remover;
- uma barra lista os blocos do catálogo que ainda não estão na tela;
- "Salvar layout" grava no servidor; "Restaurar padrão" volta ao de fábrica;
- "Sair da edição" trava a grade de novo.

Fora da edição a grade não arrasta nem redimensiona — os widgets têm botões
e formulários dentro, e um arraste acidental sobre eles atrapalharia.

## 4. Catálogo v1

Onze blocos. "Origem" diz se o bloco reaproveita um container da planilha
(ADR-0007) ou foi escrito para esta rodada.

| Id | Nome no menu | Tamanho inicial | Origem |
| --- | --- | --- | --- |
| `saldo` | Saldo do mês | 4×5 | `TotaisMes` |
| `patrimonio` | Patrimônio guardado | 4×5 | `TotalGuardado` |
| `fatura-cartao` | Fatura do cartão | 4×5 | **novo** |
| `gastos-rosca` | Gastos por categoria (rosca) | 4×6 | **novo** (Recharts) |
| `gastos-tabela` | Gastos por categoria (lista) | 4×6 | `GastosPorCategoria` |
| `despesas-diarias` | Despesas diárias | 4×6 | **novo** (Recharts) |
| `calendario` | Calendário de vencimentos | 6×7 | `CalendarioVencimentos` |
| `contas-recorrentes` | Contas recorrentes | 6×7 | `GastosFixos` |
| `saldo-inicial` | Abertura do mês | 4×4 | **novo** |
| `wishlist` | Wishlist | 4×5 | `Wishlist` |
| `lancamentos` | Lançamentos do mês | 12×8 | `TabelaLancamentos` |

Detalhes dos quatro novos:

- **Fatura do cartão** — lê `ResumoMes.por_cartao`, onde `saldo` é a dívida
  (≤ 0); mostra `-saldo`. Saldo positivo é tratado como crédito a favor, não
  como fatura negativa. Mostra o dia do vencimento e se já foi paga.
- **Gastos por categoria (rosca)** — mesma fonte da lista
  (`gastos_por_categoria`), em rosca. Usa a cor cadastrada de cada
  categoria, com uma paleta de reserva para as que não têm.
- **Despesas diárias** — calculado no cliente a partir dos lançamentos que a
  página já buscou; nenhuma chamada nova. A média divide pelos dias **já
  decorridos** quando o mês é o corrente: dividir por 30 no dia 5 daria uma
  média artificialmente baixa.
- **Abertura do mês** — saldo inicial, saldo atual e a variação entre os
  dois ("sobrou no mês" / "consumiu do saldo").

### Fora do v1, de propósito

Comparação entre meses e projeção de saldo ficaram de fora: exigiriam dado
que a API não expõe hoje, e inventar endpoint para encher o catálogo
inverteria a ordem certa (ADR-0007).

## 5. Peso da página

O painel é carregado sob demanda (`React.lazy` em `App.tsx`): traz
`react-grid-layout` e o Recharts. Quem abre na planilha — o padrão, e o uso
comum no celular — não baixa nenhum dos dois.

Medido no build: planilha ~78 kB comprimidos, painel +139 kB só quando
aberto pela primeira vez.
