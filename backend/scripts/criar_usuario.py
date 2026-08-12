"""Cria ou atualiza um usuário do sistema.

Uso:
    python -m scripts.criar_usuario

A senha é pedida de forma interativa e **não aparece na tela nem no histórico
do terminal**. Não existe opção de passar a senha por argumento de propósito:
argumentos de linha de comando ficam no histórico do shell e são visíveis para
outros processos da máquina.

Rodar de novo com um e-mail existente troca a senha dele.
"""

from __future__ import annotations

import getpass
import re
import sys

from app.database import SessionLocal, criar_tabelas
from app.models import Usuario
from app.security import gerar_hash

MINIMO_SENHA = 8
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def pedir_email() -> str:
    email = input("E-mail: ").strip().lower()
    if not EMAIL.match(email):
        print("E-mail inválido.", file=sys.stderr)
        sys.exit(1)
    return email


def pedir_senha() -> str:
    print("(a senha não aparece na tela enquanto você digita — é assim mesmo)")
    senha = getpass.getpass("Senha: ")
    if len(senha) < MINIMO_SENHA:
        print(
            f"A senha precisa ter pelo menos {MINIMO_SENHA} caracteres.",
            file=sys.stderr,
        )
        sys.exit(1)
    if senha != getpass.getpass("Repita a senha: "):
        print("As senhas não conferem.", file=sys.stderr)
        sys.exit(1)
    return senha


def main() -> None:
    criar_tabelas()

    email = pedir_email()
    senha = pedir_senha()

    sessao = SessionLocal()
    try:
        usuario = sessao.query(Usuario).filter(Usuario.email == email).one_or_none()

        if usuario is None:
            sessao.add(Usuario(email=email, senha_hash=gerar_hash(senha)))
            acao = "criado"
        else:
            usuario.senha_hash = gerar_hash(senha)
            usuario.ativo = True
            acao = "atualizado"

        sessao.commit()
        print(f"\nUsuário {email} {acao}.")
        print(
            "\nIMPORTANTE: defina SECRET_KEY no ambiente antes de publicar na "
            "internet. Sem isso, a chave é sorteada a cada inicialização e "
            "toda reinicialização desloga você."
        )
    finally:
        sessao.close()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        # Ctrl+C ou terminal sem entrada interativa: sai limpo, sem despejar um
        # traceback que não diz nada a quem só queria criar um usuário.
        print("\nCancelado. Nenhum usuário foi criado ou alterado.")
        sys.exit(1)
