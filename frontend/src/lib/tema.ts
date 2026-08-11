/** Controle do tema claro/escuro. */

import { useEffect, useState } from 'react';

export type Tema = 'claro' | 'escuro';

const CHAVE = 'planejamento:tema';

/** Lê a preferência salva; sem escolha anterior, segue o sistema. */
function temaInicial(): Tema {
  const salvo = localStorage.getItem(CHAVE);
  if (salvo === 'claro' || salvo === 'escuro') return salvo;
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'escuro'
    : 'claro';
}

export function useTema() {
  const [tema, setTema] = useState<Tema>(temaInicial);

  useEffect(() => {
    // O Tailwind está em darkMode: 'class', então basta a classe na raiz.
    document.documentElement.classList.toggle('dark', tema === 'escuro');
    localStorage.setItem(CHAVE, tema);
  }, [tema]);

  return {
    tema,
    alternar: () => setTema((t) => (t === 'claro' ? 'escuro' : 'claro')),
  };
}
