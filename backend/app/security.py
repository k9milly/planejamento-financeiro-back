"""Hash de senha e tokens de sessão.

Duas escolhas que valem explicação:

* **bcrypt** para a senha, não SHA-256 nem MD5. Hashes rápidos existem para
  serem rápidos, o que é exatamente o que um atacante quer ao testar bilhões de
  senhas. O bcrypt é lento de propósito e embute o sal.
* **JWT** para a sessão. Sem estado no servidor, o que mantém o backend simples
  e permite escalar depois. O preço é não dar para invalidar um token antes de
  ele expirar; trocar a `secret_key` derruba todas as sessões de uma vez, que é
  o botão de pânico disponível.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

ALGORITMO = "HS256"

# O bcrypt trunca em 72 bytes e, desde a versão 4.1, levanta erro em vez de
# cortar em silêncio. Truncar aqui mantém senhas longas utilizáveis.
LIMITE_BCRYPT = 72


def _em_bytes(senha: str) -> bytes:
    return senha.encode("utf-8")[:LIMITE_BCRYPT]


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(_em_bytes(senha), bcrypt.gensalt()).decode("utf-8")


def conferir_senha(senha: str, hash_guardado: str) -> bool:
    """Compara em tempo constante; devolve False para hash malformado."""
    try:
        return bcrypt.checkpw(_em_bytes(senha), hash_guardado.encode("utf-8"))
    except ValueError:
        return False


def criar_token(usuario_id: int) -> str:
    agora = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(usuario_id),
            "iat": agora,
            "exp": agora + timedelta(hours=settings.token_expira_horas),
        },
        settings.secret_key,
        algorithm=ALGORITMO,
    )


def ler_token(token: str) -> int | None:
    """Devolve o id do usuário, ou None se o token for inválido ou expirado."""
    try:
        dados = jwt.decode(token, settings.secret_key, algorithms=[ALGORITMO])
        return int(dados["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None
