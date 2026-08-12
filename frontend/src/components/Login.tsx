import { useState, type FormEvent } from 'react';
import { api } from '../lib/api';

interface Props {
  aoEntrar: () => void;
}

/** Tela de entrada. É a única coisa visível sem sessão. */
export function Login({ aoEntrar }: Props) {
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [entrando, setEntrando] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro('');
    setEntrando(true);
    try {
      await api.login(email, senha);
      aoEntrar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível entrar.');
    } finally {
      setEntrando(false);
    }
  }

  const campo =
    'w-full rounded-lg border border-roxo-100 px-3 py-2 text-sm focus:border-roxo-400 focus:outline-none dark:border-roxo-700 dark:focus:border-roxo-300';

  return (
    <div className="flex min-h-screen items-center justify-center bg-roxo-50 px-6 dark:bg-roxo-950">
      <form
        onSubmit={enviar}
        className="w-full max-w-sm rounded-xl border border-roxo-100 bg-white p-6 shadow-sm dark:border-roxo-700 dark:bg-roxo-900"
      >
        <h1 className="text-lg font-semibold text-roxo-600 dark:text-roxo-50">
          Planejamento Financeiro
        </h1>
        <p className="mt-1 text-sm text-roxo-400 dark:text-roxo-200">
          Entre para ver suas finanças.
        </p>

        <div className="mt-5 space-y-3">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="E-mail"
            // Ajuda o gerenciador de senhas do navegador a preencher sozinho.
            autoComplete="username"
            autoFocus
            required
            className={campo}
            aria-label="E-mail"
          />
          <input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            placeholder="Senha"
            autoComplete="current-password"
            required
            className={campo}
            aria-label="Senha"
          />
        </div>

        {erro && (
          <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-200">
            {erro}
          </p>
        )}

        <button
          type="submit"
          disabled={entrando}
          className="mt-5 w-full rounded-lg bg-roxo-500 px-4 py-2 text-sm font-medium text-white hover:bg-roxo-400 disabled:opacity-50"
        >
          {entrando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}
