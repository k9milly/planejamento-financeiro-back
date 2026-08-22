import { Moldura } from './Moldura';
import { moeda } from '../../lib/formato';
import type { CarteirasConta } from '../../types/api';

/**
 * Total guardado por conta — versão simplificada de "investimentos": o
 * sistema não modela aporte/rendimento individual por linha, só a reserva
 * acumulada de cada conta (ADR-0007).
 */
export function InvestimentosTabela({ porConta }: { porConta: CarteirasConta[] }) {
  const comReserva = porConta.filter((c) => Number(c.guardado) !== 0);
  const total = comReserva.reduce((s, c) => s + Number(c.guardado), 0);

  return (
    <Moldura titulo="Investimentos">
      {comReserva.length === 0 ? (
        <p className="text-white/40">Nenhuma reserva guardada ainda.</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-white/40">
              <th className="pb-1.5 font-normal">Conta</th>
              <th className="pb-1.5 text-right font-normal">Guardado</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {comReserva.map((c) => (
              <tr key={c.conta_id}>
                <td className="py-1.5 text-white/70">
                  <span className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: c.cor }}
                    />
                    {c.nome}
                  </span>
                </td>
                <td className="py-1.5 text-right tabular-nums text-white/90">
                  {moeda(c.guardado)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-white/20">
              <td className="pt-1.5 font-medium text-white/80">Total</td>
              <td className="pt-1.5 text-right font-medium tabular-nums text-white">
                {moeda(total)}
              </td>
            </tr>
          </tfoot>
        </table>
      )}
    </Moldura>
  );
}
