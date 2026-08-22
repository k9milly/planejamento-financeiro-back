import { useState, type FormEvent } from 'react';
import { Card } from './Card';
import { moeda } from '../lib/formato';
import type { CarteirasConta, Conta, Fatura, TipoConta } from '../types/api';

interface NovaConta {
  nome: string;
  cor: string;
  tipo: TipoConta;
  dia_vencimento_fatura?: number | null;
  conta_pagamento_padrao_id?: number | null;
}

interface Props {
  contas: Conta[];
  /** Fechamento atual de cada conta corrente, para mostrar quanto há em cada uma. */
  posicao: CarteirasConta[];
  /** Fatura em aberto de cada cartão ao fim do mês (`saldo` <= 0). */
  posicaoCartoes: CarteirasConta[];
  /** Fatura do mês selecionado, por cartão — para mostrar situação e valor. */
  faturas: Record<number, Fatura>;
  somenteLeitura: boolean;
  aoCriar: (dados: NovaConta) => Promise<void>;
  aoExcluir: (id: number) => Promise<void>;
  aoPagarFatura: (cartaoId: number, contaPagamentoId?: number | null) => Promise<void>;
  aoDesfazerFatura: (cartaoId: number) => Promise<void>;
  /** No modo painel, quem define a altura é a célula da grade. */
  preencher?: boolean;
}

// Cores das marcas, para a conta ser reconhecível de relance.
const SUGESTOES = ['#8d7799', '#820ad1', '#00b1ea', '#f97316', '#22c55e'];

/**
 * Container de contas e cartões: onde o dinheiro está, e quanto se deve.
 *
 * Um cartão de crédito é modelado como uma conta também (ver ADR-0002), mas
 * mostrado numa seção separada — sua "fatura em aberto" é dívida, não
 * dinheiro disponível, e não entra no patrimônio somado abaixo.
 */
export function GerenciadorContas({
  contas,
  posicao,
  posicaoCartoes,
  faturas,
  somenteLeitura,
  aoCriar,
  aoExcluir,
  aoPagarFatura,
  aoDesfazerFatura,
  preencher,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [tipo, setTipo] = useState<TipoConta>('corrente');
  const [nome, setNome] = useState('');
  const [cor, setCor] = useState(SUGESTOES[0]);
  const [diaVencimento, setDiaVencimento] = useState('10');
  const [contaPadraoId, setContaPadraoId] = useState('');
  const [erro, setErro] = useState('');
  const [pagandoCartaoId, setPagandoCartaoId] = useState<number | null>(null);

  const contasCorrentes = contas.filter((c) => c.tipo === 'corrente');
  const cartoes = contas.filter((c) => c.tipo === 'cartao_credito');

  const porConta = new Map(posicao.map((p) => [p.conta_id, p]));
  const porCartao = new Map(posicaoCartoes.map((p) => [p.conta_id, p]));
  const patrimonio = posicao.reduce(
    (soma, p) => soma + Number(p.saldo) + Number(p.guardado),
    0,
  );

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');
    try {
      await aoCriar({
        nome,
        cor,
        tipo,
        dia_vencimento_fatura: tipo === 'cartao_credito' ? Number(diaVencimento) : null,
        conta_pagamento_padrao_id:
          tipo === 'cartao_credito' && contaPadraoId ? Number(contaPadraoId) : null,
      });
      setNome('');
      setAberto(false);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível salvar.');
    }
  }

  const campo =
    'rounded-lg border border-roxo-100 px-3 py-2 text-sm focus:border-roxo-400 focus:outline-none dark:border-roxo-700 dark:focus:border-roxo-300';

  return (
    <Card
      preencher={preencher}
      titulo="Contas"
      acao={
        !somenteLeitura && (
          <button
            onClick={() => setAberto(!aberto)}
            className="text-xs font-medium text-roxo-400 hover:text-roxo-600 dark:text-roxo-200 dark:hover:text-roxo-50"
          >
            {aberto ? 'Cancelar' : '+ Nova'}
          </button>
        )
      }
    >
      {aberto && (
        <form onSubmit={enviar} className="mb-4 space-y-2">
          <div className="flex overflow-hidden rounded-lg border border-roxo-100 text-xs dark:border-roxo-700">
            <button
              type="button"
              onClick={() => setTipo('corrente')}
              className={`flex-1 px-3 py-1.5 font-medium ${
                tipo === 'corrente'
                  ? 'bg-roxo-500 text-white'
                  : 'text-roxo-400 dark:text-roxo-200'
              }`}
            >
              Conta
            </button>
            <button
              type="button"
              onClick={() => setTipo('cartao_credito')}
              className={`flex-1 px-3 py-1.5 font-medium ${
                tipo === 'cartao_credito'
                  ? 'bg-roxo-500 text-white'
                  : 'text-roxo-400 dark:text-roxo-200'
              }`}
            >
              Cartão de crédito
            </button>
          </div>

          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder={tipo === 'corrente' ? 'Nome (ex.: Nubank)' : 'Nome do cartão'}
            className={`${campo} w-full`}
            required
          />

          {tipo === 'cartao_credito' && (
            <div className="flex flex-wrap gap-2">
              <input
                type="number"
                min="1"
                max="31"
                value={diaVencimento}
                onChange={(e) => setDiaVencimento(e.target.value)}
                className={`${campo} w-24`}
                aria-label="Dia do vencimento da fatura"
                required
              />
              <select
                value={contaPadraoId}
                onChange={(e) => setContaPadraoId(e.target.value)}
                className={`${campo} flex-1`}
                aria-label="Conta que paga por padrão"
              >
                <option value="">Escolher na hora de pagar</option>
                {contasCorrentes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nome}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex items-center gap-2">
            {SUGESTOES.map((opcao) => (
              <button
                key={opcao}
                type="button"
                onClick={() => setCor(opcao)}
                aria-label={`Cor ${opcao}`}
                className={`h-6 w-6 rounded-full border-2 ${
                  cor === opcao
                    ? 'border-roxo-500 dark:border-roxo-100'
                    : 'border-transparent'
                }`}
                style={{ backgroundColor: opcao }}
              />
            ))}
            <button
              type="submit"
              className="ml-auto rounded-lg bg-roxo-500 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400"
            >
              Adicionar
            </button>
          </div>
          {erro && <p className="text-sm text-rose-600">{erro}</p>}
        </form>
      )}

      {contasCorrentes.length === 0 ? (
        <p className="text-sm text-roxo-300">Nenhuma conta cadastrada.</p>
      ) : (
        <ul className="divide-y divide-roxo-100 dark:divide-roxo-700">
          {contasCorrentes.map((conta) => {
            const p = porConta.get(conta.id);
            const saldo = Number(p?.saldo ?? 0);
            const guardado = Number(p?.guardado ?? 0);
            return (
              <li key={conta.id} className="group flex items-center gap-3 py-2">
                <span
                  className="h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: conta.cor }}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-roxo-600 dark:text-roxo-100">
                    {conta.nome}
                  </p>
                  {guardado !== 0 && (
                    <p className="text-xs text-roxo-300">
                      guardado: {moeda(guardado)}
                    </p>
                  )}
                </div>
                <span
                  className={`tabular-nums text-sm font-medium ${
                    saldo < 0
                      ? 'text-rose-600 dark:text-rose-400'
                      : 'text-roxo-700 dark:text-roxo-50'
                  }`}
                >
                  {moeda(saldo)}
                </span>
                {!somenteLeitura && (
                  <button
                    onClick={() => void aoExcluir(conta.id)}
                    className="text-xs text-roxo-200 opacity-0 hover:text-rose-600 group-hover:opacity-100"
                    aria-label={`Excluir ${conta.nome}`}
                  >
                    ✕
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {posicao.length > 0 && (
        <div className="mt-3 flex justify-between border-t-2 border-roxo-100 pt-3 text-sm dark:border-roxo-600">
          <span className="text-roxo-500 dark:text-roxo-200">
            Patrimônio
            <span className="ml-1 text-xs text-roxo-300">
              (saldo + guardado)
            </span>
          </span>
          <span className="tabular-nums font-semibold text-roxo-700 dark:text-roxo-50">
            {moeda(patrimonio)}
          </span>
        </div>
      )}
      {/* Saldo disponível: compras no crédito entram na fatura, não descontam
          daqui até você pagá-la — ver seção "Cartões de crédito" abaixo. */}
      {cartoes.length > 0 && (
        <p className="mt-2 text-xs text-roxo-300">
          Compras no crédito entram na fatura, não descontam daqui até você
          pagá-la.
        </p>
      )}

      {cartoes.length > 0 && (
        <div className="mt-5 border-t border-roxo-100 pt-4 dark:border-roxo-700">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-roxo-400 dark:text-roxo-200">
            Cartões de crédito
          </h3>
          <ul className="divide-y divide-roxo-100 dark:divide-roxo-700">
            {cartoes.map((cartao) => {
              const pc = porCartao.get(cartao.id);
              const emAberto = Math.max(0, -Number(pc?.saldo ?? 0));
              const fatura = faturas[cartao.id];
              const pago = fatura?.situacao === 'pago';
              return (
                <li key={cartao.id} className="py-2">
                  <div className="group flex items-center gap-3">
                    <span
                      className="h-3 w-3 shrink-0 rounded-full"
                      style={{ backgroundColor: cartao.cor }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-roxo-600 dark:text-roxo-100">
                        💳 {cartao.nome}
                      </p>
                      <p className="text-xs text-roxo-300">
                        vence dia {cartao.dia_vencimento_fatura}
                        {pago && ' · fatura paga'}
                      </p>
                    </div>
                    <span className="tabular-nums text-sm font-medium text-rose-600 dark:text-rose-400">
                      {moeda(emAberto)}
                    </span>
                    {!somenteLeitura && (
                      <button
                        onClick={() => void aoExcluir(cartao.id)}
                        className="text-xs text-roxo-200 opacity-0 hover:text-rose-600 group-hover:opacity-100"
                        aria-label={`Excluir ${cartao.nome}`}
                      >
                        ✕
                      </button>
                    )}
                  </div>

                  {!somenteLeitura && emAberto > 0 && !pago && (
                    <FormularioPagarFatura
                      cartao={cartao}
                      contas={contasCorrentes}
                      aberto={pagandoCartaoId === cartao.id}
                      aoAbrir={() => setPagandoCartaoId(cartao.id)}
                      aoFechar={() => setPagandoCartaoId(null)}
                      aoPagar={async (contaPagamentoId) => {
                        await aoPagarFatura(cartao.id, contaPagamentoId);
                        setPagandoCartaoId(null);
                      }}
                    />
                  )}
                  {!somenteLeitura && pago && (
                    <button
                      onClick={() => void aoDesfazerFatura(cartao.id)}
                      className="mt-1 text-xs text-roxo-300 hover:text-rose-600"
                    >
                      Desfazer pagamento
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}

function FormularioPagarFatura({
  cartao,
  contas,
  aberto,
  aoAbrir,
  aoFechar,
  aoPagar,
}: {
  cartao: Conta;
  contas: Conta[];
  aberto: boolean;
  aoAbrir: () => void;
  aoFechar: () => void;
  aoPagar: (contaPagamentoId: number | null) => Promise<void>;
}) {
  const [contaId, setContaId] = useState(
    cartao.conta_pagamento_padrao_id ? String(cartao.conta_pagamento_padrao_id) : '',
  );
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  if (!aberto) {
    return (
      <button
        onClick={aoAbrir}
        className="mt-1 text-xs font-medium text-roxo-400 hover:text-roxo-600 dark:text-roxo-200 dark:hover:text-roxo-50"
      >
        Marcar fatura como paga
      </button>
    );
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setErro('');
        setSalvando(true);
        try {
          await aoPagar(contaId ? Number(contaId) : null);
        } catch (err) {
          setErro(err instanceof Error ? err.message : 'Não foi possível pagar.');
        } finally {
          setSalvando(false);
        }
      }}
      className="mt-2 flex flex-wrap items-center gap-2"
    >
      <select
        value={contaId}
        onChange={(e) => setContaId(e.target.value)}
        className="rounded-lg border border-roxo-100 px-2 py-1 text-xs dark:border-roxo-700"
        aria-label={`Conta que paga a fatura do ${cartao.nome}`}
        required
      >
        <option value="">De qual conta?</option>
        {contas.map((c) => (
          <option key={c.id} value={c.id}>
            {c.nome}
          </option>
        ))}
      </select>
      <button
        type="submit"
        disabled={salvando}
        className="rounded-lg bg-roxo-500 px-3 py-1 text-xs font-medium text-white hover:bg-roxo-400 disabled:opacity-50"
      >
        {salvando ? 'Pagando…' : 'Confirmar'}
      </button>
      <button
        type="button"
        onClick={aoFechar}
        className="text-xs text-roxo-300 hover:text-roxo-600"
      >
        Cancelar
      </button>
      {erro && <p className="w-full text-xs text-rose-600">{erro}</p>}
    </form>
  );
}
