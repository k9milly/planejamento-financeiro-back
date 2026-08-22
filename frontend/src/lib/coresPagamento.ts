/**
 * Cor de cada forma de pagamento, escolhida pela usuária e guardada no
 * servidor — não no navegador.
 *
 * Fica no servidor de propósito: a usuária usa o app tanto no celular quanto
 * no PC, e uma preferência salva só em `localStorage` não apareceria igual
 * nos dois. Ver `CorFormaPagamento` e `app/routers/preferencias.py` no
 * backend.
 */

import { useEffect, useState } from 'react';
import { api } from './api';
import type { FormaPagamento } from '../types/api';

const PADRAO: Record<FormaPagamento, string> = {
  dinheiro: '#22c55e',
  debito: '#0ea5e9',
  pix: '#14b8a6',
  credito: '#f97316',
};

export function useCoresPagamento() {
  const [cores, setCores] = useState<Record<FormaPagamento, string>>(PADRAO);

  useEffect(() => {
    api
      .listarCoresPagamento()
      .then((lista) => {
        setCores((atual) => {
          const novo = { ...atual };
          for (const item of lista) novo[item.forma_pagamento] = item.cor;
          return novo;
        });
      })
      .catch(() => {
        // Sem sessão ainda, ou falha de rede: fica no padrão local.
      });
  }, []);

  async function definirCor(forma: FormaPagamento, cor: string) {
    setCores((atual) => ({ ...atual, [forma]: cor }));
    await api.definirCorPagamento(forma, cor);
  }

  return { cores, definirCor };
}
