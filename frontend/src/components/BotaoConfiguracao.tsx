import { useEffect, useRef, useState, type ReactNode } from 'react';

interface Props {
  rotulo: string;
  children: ReactNode;
}

/**
 * Botão discreto (engrenagem, cores do sistema) que abre um painel flutuante
 * pequeno ao lado. Esconde telas de configuração pouco usadas (categorias,
 * cores de pagamento) atrás de um clique, em vez de deixá-las sempre visíveis.
 */
export function BotaoConfiguracao({ rotulo, children }: Props) {
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    function aoClicarFora(evento: MouseEvent) {
      if (raiz.current && !raiz.current.contains(evento.target as Node)) {
        setAberto(false);
      }
    }
    document.addEventListener('mousedown', aoClicarFora);
    return () => document.removeEventListener('mousedown', aoClicarFora);
  }, [aberto]);

  return (
    <div ref={raiz} className="relative inline-block">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-label={rotulo}
        title={rotulo}
        className="rounded-full p-1.5 text-roxo-300 hover:bg-roxo-100 hover:text-roxo-500 dark:text-roxo-400 dark:hover:bg-roxo-700 dark:hover:text-roxo-100"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path
            fillRule="evenodd"
            d="M8.34 1.804A1 1 0 019.32 1h1.36a1 1 0 01.98.804l.331 1.652a6.993 6.993 0 011.929 1.115l1.598-.54a1 1 0 011.186.447l.68 1.178a1 1 0 01-.223 1.29l-1.27 1.06a7.05 7.05 0 010 2.227l1.27 1.06a1 1 0 01.223 1.29l-.68 1.178a1 1 0 01-1.187.447l-1.596-.54a6.993 6.993 0 01-1.93 1.115l-.33 1.652a1 1 0 01-.98.804H9.32a1 1 0 01-.98-.804l-.331-1.652a6.993 6.993 0 01-1.929-1.115l-1.598.54a1 1 0 01-1.186-.447l-.68-1.178a1 1 0 01.223-1.29l1.27-1.06a7.05 7.05 0 010-2.227l-1.27-1.06a1 1 0 01-.223-1.29l.68-1.178a1 1 0 011.187-.447l1.596.54A6.993 6.993 0 018.01 3.456l.33-1.652zM10 13a3 3 0 100-6 3 3 0 000 6z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {aberto && (
        <div className="absolute right-0 z-20 mt-2 w-80 max-w-[90vw]">
          {children}
        </div>
      )}
    </div>
  );
}
