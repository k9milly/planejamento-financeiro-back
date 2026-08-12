/**
 * Guarda o token da sessão.
 *
 * Fica em `localStorage` para sobreviver ao fechar a aba — sem isso, você
 * refaria o login toda vez que abrisse o app no celular, que é justamente o
 * uso principal. A troca é ficar acessível a JavaScript da própria página, o
 * que só vira problema se houver XSS; como o app não renderiza HTML de
 * terceiros, o risco é baixo.
 */

const CHAVE = 'planejamento:token';

/** Avisa o app quando o token cai, para ele voltar à tela de login. */
let aoExpirar: (() => void) | null = null;

export const sessao = {
  ler: () => localStorage.getItem(CHAVE),

  guardar(token: string) {
    localStorage.setItem(CHAVE, token);
  },

  limpar() {
    localStorage.removeItem(CHAVE);
  },

  /** Registra o callback chamado quando a API responder 401. */
  observarExpiracao(callback: () => void) {
    aoExpirar = callback;
  },

  expirou() {
    localStorage.removeItem(CHAVE);
    aoExpirar?.();
  },
};
