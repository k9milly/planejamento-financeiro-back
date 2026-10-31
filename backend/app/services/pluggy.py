"""Cliente da Pluggy — só o que o open finance precisa daqui.

## Por que não o SDK oficial

O `pluggy-sdk` existe e funciona, mas é um cliente gerado do OpenAPI deles:
**3,2 MB em 309 arquivos**, cobrindo a API inteira (boletos, PIX automático,
investimentos, bills...), e traz `urllib3` e `python-dateutil` junto. Deste
tudo, o backend usa **duas** chamadas HTTP.

É a mesma conta que o ADR-12 já fez ao escolher `pypdf` em vez de
`pdfplumber`: o que entra na imagem precisa pagar o que ocupa. Aqui as duas
chamadas cabem em trinta linhas de `httpx`, que já estava no projeto.

Vale o aviso para quem for ler depois: o pacote `pluggy` que aparece instalado
**não é** esta Pluggy — é o sistema de plugins do pytest, que veio junto com
ele. Nomes iguais, projetos sem nenhuma relação.

## As duas chamadas

Conferidas lendo o SDK oficial, não de memória:

    POST /auth           {clientId, clientSecret}   -> {apiKey}
    POST /connect_token  {options: {clientUserId}}  -> {accessToken}

A `apiKey` do primeiro passo vale por duas horas e autentica o segundo, no
cabeçalho `X-API-KEY`. Não guardamos ela: o connect token é pedido raramente
(uma vez por conexão de banco) e um cache traria invalidação para manter em
troca de uma requisição.

**`clientUserId` fica dentro de `options`**, e não no corpo raiz — é onde o
modelo real da Pluggy o coloca. O exemplo que circula por aí passa
`client_user_id` direto na chamada, o que não corresponde à API: não existe
nem o método `create_connect_token`, nem a classe `PluggyClient` que esse
exemplo importa.
"""

from __future__ import annotations

import httpx

from app.config import settings

# Tempo de paciência com a Pluggy. Curto de propósito: quem está esperando é
# uma pessoa com a tela de conectar banco aberta, e um erro claro em dez
# segundos é melhor do que um carregando infinito.
TEMPO_LIMITE = httpx.Timeout(10.0)


class PluggyIndisponivel(RuntimeError):
    """A Pluggy não respondeu, ou respondeu erro. O router vira isso em 502."""


class PluggyNaoConfigurada(RuntimeError):
    """Faltam as credenciais no ambiente. O router vira isso em 503."""


def _api_key(cliente: httpx.Client) -> str:
    """Autentica a aplicação e devolve a chave de duas horas."""
    resposta = cliente.post(
        "/auth",
        json={
            "clientId": settings.pluggy_client_id,
            "clientSecret": settings.pluggy_client_secret,
        },
    )
    if resposta.status_code == httpx.codes.FORBIDDEN:
        # A Pluggy responde 403 para credencial errada. Mensagem própria
        # porque "403" sozinho mandaria procurar o problema no lugar errado.
        raise PluggyIndisponivel(
            "A Pluggy recusou as credenciais desta aplicação. Confira "
            "PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no ambiente."
        )
    resposta.raise_for_status()
    return resposta.json()["apiKey"]


def criar_connect_token(client_user_id: str) -> str:
    """Um token de curta duração para o navegador abrir o Pluggy Connect.

    É o único segredo que chega ao frontend, e ele não serve para ler dado
    nenhum: só para abrir o widget de conexão. O `clientId` e o
    `clientSecret` nunca saem daqui — é a razão de esta rota existir no
    backend em vez de o frontend falar direto com a Pluggy.

    `client_user_id` é um identificador **nosso**, livre, que a Pluggy guarda
    junto do item criado. Serve para sabermos de quem é a conexão quando o
    webhook chegar.
    """
    if not settings.pluggy_configurada:
        raise PluggyNaoConfigurada(
            "Open finance não está configurado nesta instalação."
        )

    try:
        with httpx.Client(
            base_url=settings.pluggy_base_url, timeout=TEMPO_LIMITE
        ) as cliente:
            chave = _api_key(cliente)
            resposta = cliente.post(
                "/connect_token",
                json={"options": {"clientUserId": client_user_id}},
                headers={"X-API-KEY": chave},
            )
            resposta.raise_for_status()
            return resposta.json()["accessToken"]
    except PluggyIndisponivel:
        raise
    except httpx.HTTPStatusError as erro:
        raise PluggyIndisponivel(
            f"A Pluggy respondeu {erro.response.status_code}."
        ) from erro
    except httpx.HTTPError as erro:
        raise PluggyIndisponivel("Não foi possível falar com a Pluggy.") from erro
