import { Moldura } from './Moldura';
import { moeda } from '../../lib/formato';
import type { CarteirasConta } from '../../types/api';

/**
 * Lista de contas (correntes, ver ADR-0002) com o saldo de cada uma, e o
 * total. Um dropdown filtra para uma conta só — a escolha é `config.contaId`,
 * guardada na instância (ADR-0008: `config` é por widget, não global).
 */
export function TodasContas({
  porConta,
  saldoTotal,
  contaId,
  aoMudarConta,
}: {
  porConta: CarteirasConta[];
  saldoTotal: string;
  contaId: number | null;
  aoMudarConta: (contaId: number | null) => void;
}) {
  const filtradas = contaId ? porConta.filter((c) => c.conta_id === contaId) : porConta;
  const total = contaId
    ? (filtradas[0]?.saldo ?? '0')
    : saldoTotal;

  return (
    <Moldura
      titulo="Contas"
      acao={
        porConta.length > 1 && (
          <select
            value={contaId ?? ''}
            onChange={(e) => aoMudarConta(e.target.value ? Number(e.target.value) : null)}
            className="rounded-md border border-white/10 bg-roxo-950 px-1.5 py-0.5 text-xs text-white/80"
          >
            <option value="">Todas</option>
            {porConta.map((c) => (
              <option key={c.conta_id} value={c.conta_id}>
                {c.nome}
              </option>
            ))}
          </select>
        )
      }
    >
      <p className="text-xl font-semibold tabular-nums text-white">{moeda(total)}</p>
      <ul className="mt-2 space-y-1">
        {filtradas.map((c) => (
          <li key={c.conta_id} className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-white/60">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: c.cor }}
              />
              {c.nome}
            </span>
            <span className="tabular-nums text-white/80">{moeda(c.saldo)}</span>
          </li>
        ))}
      </ul>
    </Moldura>
  );
}
