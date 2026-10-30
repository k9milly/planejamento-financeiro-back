"""Cria ou atualiza um usuário do sistema.

Uso:
    python -m scripts.criar_usuario

A senha é pedida de forma interativa e **não aparece na tela nem no histórico
do terminal**. Não existe opção de passar a senha por argumento de propósito:
argumentos de linha de comando ficam no histórico do shell e são visíveis para
outros processos da máquina.

Rodar de novo com um e-mail existente troca a senha dele.

## Por que o script cria um espaço (ADR-15)

Desde o ADR-15, dado financeiro pertence a um espaço, e o filtro automático da
sessão usa o espaço atual de quem está logado. Um usuário sem espaço entra no
sistema e não vê nada — toda consulta volta vazia. Então criar usuário sem
criar espaço produziria uma conta inútil, e o script faz as duas coisas.

Este script roda **fora** de uma requisição HTTP, logo fora do carimbo
automático de `espaco_id`: aqui o vínculo é escrito na mão, de propósito.
"""

from __future__ import annotations

import getpass
import re
import sys

from app.database import SessionLocal, exigir_schema
from app.models import Espaco, MembroEspaco, PapelMembro, Usuario
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
    exigir_schema()

    email = pedir_email()
    senha = pedir_senha()

    sessao = SessionLocal()
    try:
        usuario = sessao.query(Usuario).filter(Usuario.email == email).one_or_none()

        if usuario is None:
            # O espaço nasce junto. O nome sai do e-mail só para não pedir mais
            # uma resposta a quem está criando a conta; dá para renomear depois
            # em `PATCH /espacos/{id}`.
            espaco = Espaco(nome=email.split("@")[0][:80])
            sessao.add(espaco)
            sessao.flush()

            usuario = Usuario(
                email=email,
                senha_hash=gerar_hash(senha),
                espaco_atual_id=espaco.id,
            )
            sessao.add(usuario)
            sessao.flush()

            sessao.add(
                MembroEspaco(
                    espaco_id=espaco.id,
                    usuario_id=usuario.id,
                    papel=PapelMembro.DONO,
                )
            )
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
