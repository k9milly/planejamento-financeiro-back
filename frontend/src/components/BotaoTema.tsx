import type { Tema } from '../lib/tema';

interface Props {
  tema: Tema;
  aoAlternar: () => void;
}

/** Botão de alternância entre tema claro e escuro. */
export function BotaoTema({ tema, aoAlternar }: Props) {
  const escuro = tema === 'escuro';

  return (
    <button
      onClick={aoAlternar}
      // O rótulo diz para onde a ação leva, não o estado atual — é o que o
      // leitor de tela precisa anunciar.
      aria-label={escuro ? 'Ativar modo claro' : 'Ativar modo escuro'}
      title={escuro ? 'Modo claro' : 'Modo escuro'}
      className="rounded-lg border border-roxo-200 p-2 text-roxo-500 hover:bg-roxo-100 dark:border-roxo-600 dark:text-roxo-100 dark:hover:bg-roxo-700"
    >
      {escuro ? <IconeSol /> : <IconeLua />}
    </button>
  );
}

function IconeSol() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function IconeLua() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}
