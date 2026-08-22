import { api } from '../lib/api';
import { NOMES_MESES } from '../lib/formato';
import { BotaoConfiguracao } from '../components/BotaoConfiguracao';
import { Cabecalho } from '../components/Cabecalho';
import { CalendarioVencimentos } from '../components/CalendarioVencimentos';
import { CoresPagamento } from '../components/CoresPagamento';
import { FormularioLancamento } from '../components/FormularioLancamento';
import { GastosFixos } from '../components/GastosFixos';
import { GastosPorCategoria } from '../components/GastosPorCategoria';
import { GerenciadorCategorias } from '../components/GerenciadorCategorias';
import { GerenciadorContas } from '../components/GerenciadorContas';
import { ImportarExtrato } from '../components/ImportarExtrato';
import { TabelaLancamentos } from '../components/TabelaLancamentos';
import { TotaisMes } from '../components/TotaisMes';
import { TotalGuardado } from '../components/TotalGuardado';
import { Wishlist } from '../components/Wishlist';
import type { PropsModo } from './tiposModo';

/** Modo "planilha": as 12 páginas do ano, uma por mês. Comportamento atual do app. */
export function ModoPlanilha({
  tema,
  alternar,
  anos,
  anoAtual,
  setAnoAtual,
  mesAtual,
  setMesAtual,
  resumo,
  lancamentos,
  categorias,
  contas,
  gastosFixos,
  desejos,
  faturas,
  erro,
  setErro,
  importando,
  setImportando,
  editandoLancamento,
  setEditandoLancamento,
  recarregar,
  acao,
  alternarGastoFixo,
  aposMudarCategorias,
  criarCategoriaInline,
  atualizarLancamento,
  comAnos,
  aoSair,
  modo,
  aoDefinirModo,
}: PropsModo) {
  const mes = resumo?.meses[mesAtual - 1];
  const arquivado = resumo?.arquivado ?? false;

  return (
    <div className="min-h-screen bg-roxo-50 dark:bg-roxo-950">
      <Cabecalho
        tema={tema}
        aoAlternarTema={alternar}
        anos={anos}
        anoAtual={anoAtual}
        aoTrocarAno={(ano) => {
          setEditandoLancamento(null);
          setAnoAtual(ano);
        }}
        aoCriarAno={(ano) => comAnos(() => api.criarAno(ano), ano)}
        aoArquivarAno={(ano) => comAnos(() => api.arquivarAno(ano))}
        aoDesarquivarAno={(ano) => comAnos(() => api.desarquivarAno(ano))}
        mesAtual={mesAtual}
        aoTrocarMes={(numero) => {
          setEditandoLancamento(null);
          setMesAtual(numero);
        }}
        modo={modo}
        aoDefinirModo={aoDefinirModo}
        aoSair={aoSair}
        acoes={
          !arquivado && (
            <button
              onClick={() => setImportando((v) => !v)}
              className="rounded-lg border border-roxo-200 px-3 py-1.5 text-xs font-medium text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
            >
              Importar extrato
            </button>
          )
        }
      />

      <main className="mx-auto max-w-6xl px-6 py-6">
        {erro && (
          <p className="mb-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-200">
            {erro}
          </p>
        )}

        {importando && !arquivado && (
          <div className="mb-5">
            <ImportarExtrato
              ano={anoAtual}
              categorias={categorias}
              contas={contas}
              aoFechar={() => setImportando(false)}
              aoImportar={recarregar}
            />
          </div>
        )}

        {resumo && mes && (
          <div className="grid gap-5 lg:grid-cols-3">
            <TotalGuardado resumo={resumo} />
            <TotaisMes mes={mes} />
            <GastosPorCategoria mes={mes} categorias={categorias} />

            <GerenciadorContas
              contas={contas}
              posicao={mes.por_conta}
              posicaoCartoes={mes.por_cartao}
              faturas={faturas}
              somenteLeitura={arquivado}
              aoCriar={async (dados) => {
                await api.criarConta({ ...dados, ordem: contas.length });
                await recarregar();
              }}
              aoExcluir={async (id) => {
                await api.excluirConta(id);
                await recarregar();
              }}
              aoPagarFatura={async (cartaoId, contaPagamentoId) => {
                // Erros ficam para o mini-formulário mostrar (a conta pode
                // faltar), então não são capturados aqui.
                await api.pagarFatura(anoAtual, cartaoId, mesAtual, contaPagamentoId);
                await recarregar();
              }}
              aoDesfazerFatura={async (cartaoId) => {
                try {
                  await api.desfazerFatura(anoAtual, cartaoId, mesAtual);
                  await recarregar();
                } catch (e) {
                  setErro(
                    e instanceof Error
                      ? e.message
                      : 'Não foi possível desfazer o pagamento.',
                  );
                }
              }}
            />

            <GastosFixos
              gastos={gastosFixos}
              contas={contas}
              mes={mesAtual}
              somenteLeitura={arquivado}
              aoCriar={acao(api.criarGastoFixo)}
              aoAtualizar={acao(api.atualizarGastoFixo)}
              aoAlternar={alternarGastoFixo}
              aoExcluir={acao(api.excluirGastoFixo)}
            />

            <CalendarioVencimentos
              gastos={gastosFixos}
              cartoes={contas.filter((c) => c.tipo === 'cartao_credito')}
              faturas={faturas}
              ano={anoAtual}
              mes={mesAtual}
              somenteLeitura={arquivado}
              aoAlternar={alternarGastoFixo}
              aoAlternarFatura={async (cartao, pago) => {
                try {
                  if (pago) {
                    await api.pagarFatura(
                      anoAtual,
                      cartao.id,
                      mesAtual,
                      cartao.conta_pagamento_padrao_id,
                    );
                  } else {
                    await api.desfazerFatura(anoAtual, cartao.id, mesAtual);
                  }
                  await recarregar();
                } catch (e) {
                  setErro(
                    e instanceof Error
                      ? e.message
                      : 'Não foi possível atualizar a fatura.',
                  );
                }
              }}
            />

            <Wishlist
              desejos={desejos}
              totalGuardado={resumo.total_guardado}
              somenteLeitura={arquivado}
              aoCriar={acao(api.criarDesejo)}
              aoAtualizar={acao(api.atualizarDesejo)}
              aoExcluir={acao(api.excluirDesejo)}
            />

            <div className="lg:col-span-3">
              {!arquivado && (
                <FormularioLancamento
                  // Remonta ao trocar entre "novo" e "editando algo": mais
                  // simples e menos propenso a erro do que sincronizar cada
                  // campo via useEffect a cada troca de alvo.
                  key={editandoLancamento?.id ?? 'novo'}
                  ano={anoAtual}
                  mes={mesAtual}
                  contas={contas}
                  categorias={categorias}
                  aoSalvar={acao(api.criarLancamento)}
                  aoCriarCategoria={criarCategoriaInline}
                  lancamento={editandoLancamento}
                  aoAtualizar={atualizarLancamento}
                  aoCancelar={() => setEditandoLancamento(null)}
                  menuCategorias={
                    <BotaoConfiguracao rotulo="Configurar categorias">
                      <GerenciadorCategorias
                        categorias={categorias}
                        somenteLeitura={arquivado}
                        aoCriar={async (nome, cor) => {
                          await api.criarCategoria(nome, cor);
                          await aposMudarCategorias();
                        }}
                        aoRenomear={async (id, nome) => {
                          await api.atualizarCategoria(id, { nome });
                          await aposMudarCategorias();
                        }}
                        aoMudarCor={async (id, cor) => {
                          await api.atualizarCategoria(id, { cor });
                          await aposMudarCategorias();
                        }}
                        aoExcluir={async (id) => {
                          await api.excluirCategoria(id);
                          await aposMudarCategorias();
                        }}
                      />
                    </BotaoConfiguracao>
                  }
                  menuFormaPagamento={
                    <BotaoConfiguracao rotulo="Configurar cores de pagamento">
                      <CoresPagamento />
                    </BotaoConfiguracao>
                  }
                />
              )}
              <TabelaLancamentos
                titulo={NOMES_MESES[mesAtual - 1]}
                lancamentos={lancamentos}
                contas={contas}
                somenteLeitura={arquivado}
                aoEditar={setEditandoLancamento}
                aoExcluir={acao(api.excluirLancamento)}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
