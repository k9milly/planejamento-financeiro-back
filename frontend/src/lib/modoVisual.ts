/**
 * Escolha entre os dois modos de ver o mesmo mês (ADR-0004).
 *
 * `planilha` é a tela original, de containers fixos; `estatico` é o painel de
 * blocos que a usuária arruma como quiser. A escolha mora no `localStorage`,
 * não no servidor: é preferência de aparelho — faz sentido abrir o painel no
 * PC e a planilha no celular, onde arrastar bloco é desconfortável.
 */

import { useEffect, useState } from 'react';

export type ModoVisual = 'planilha' | 'estatico';

const CHAVE = 'planejamento:modo';

function modoInicial(): ModoVisual {
  return localStorage.getItem(CHAVE) === 'estatico' ? 'estatico' : 'planilha';
}

export function useModoVisual() {
  const [modo, definir] = useState<ModoVisual>(modoInicial);

  useEffect(() => {
    localStorage.setItem(CHAVE, modo);
  }, [modo]);

  return {
    modo,
    definir,
    alternar: () =>
      definir((m) => (m === 'planilha' ? 'estatico' : 'planilha')),
  };
}
