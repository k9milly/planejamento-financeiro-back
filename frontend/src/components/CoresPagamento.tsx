import { Card } from './Card';
import { ESTILO_FORMA_PAGAMENTO } from '../lib/formato';
import { useCoresPagamento } from '../lib/coresPagamento';
import type { FormaPagamento } from '../types/api';

const FORMAS = Object.keys(ESTILO_FORMA_PAGAMENTO) as FormaPagamento[];

/**
 * Deixa escolher a cor de cada forma de pagamento (débito, crédito, pix,
 * dinheiro). Puramente cosmético — muda só como o rótulo aparece na tabela,
 * nunca os dados. Guardado no servidor, igual em qualquer aparelho; ver
 * `lib/coresPagamento.ts`.
 */
export function CoresPagamento() {
  const { cores, definirCor } = useCoresPagamento();

  return (
    <Card titulo="Cores da forma de pagamento">
      <ul className="space-y-2">
        {FORMAS.map((forma) => (
          <li key={forma} className="flex items-center justify-between gap-3">
            <span
              className="text-sm font-medium"
              style={{ color: cores[forma] }}
            >
              {ESTILO_FORMA_PAGAMENTO[forma].rotulo}
            </span>
            <input
              type="color"
              value={cores[forma]}
              onChange={(e) => definirCor(forma, e.target.value)}
              className="h-7 w-10 cursor-pointer rounded border border-roxo-100 bg-transparent dark:border-roxo-700"
              aria-label={`Cor de ${ESTILO_FORMA_PAGAMENTO[forma].rotulo}`}
            />
          </li>
        ))}
      </ul>
    </Card>
  );
}
