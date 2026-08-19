"""Lançamento rápido por mensagem do Telegram.

Fluxo: você manda "15, brownie, mercado pago" no chat com o bot, e ele cria um
lançamento de saída na hora, com a data do envio da mensagem, tentando
reconhecer a conta pelo texto e sugerindo categoria pelas mesmas regras da
importação de extrato.

Este endpoint não usa a autenticação por sessão do resto da API — o Telegram
não tem como carregar um token nosso. A proteção é outra, em duas camadas:
um segredo no cabeçalho (definido ao registrar o webhook, via `setWebhook`)
e uma lista de exatamente um chat autorizado. Mensagens de qualquer outra
origem são ignoradas em silêncio, sem confirmar nem negar que o bot existe.

O recurso fica desativado sozinho (a rota responde 404) enquanto as três
variáveis TELEGRAM_* não estiverem configuradas — ver `app/config.py`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Ano, Conta, Lancamento, RegraCategorizacao, TipoLancamento
from app.services.categorizacao import normalizar, sugerir_categoria
from app.services.telegram_parser import ErroInterpretacao, escolher_conta, interpretar

router = APIRouter(prefix="/webhooks/telegram", tags=["telegram"])

_API_TELEGRAM = "https://api.telegram.org"


@router.post("", include_in_schema=False, summary="Recebe atualizações do bot")
async def receber(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not (
        settings.telegram_bot_token
        and settings.telegram_webhook_secret
        and settings.telegram_chat_id
    ):
        # Recurso não configurado: não expõe nem que a rota existe de verdade.
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    corpo = await request.json()
    mensagem = corpo.get("message")
    if not mensagem or "text" not in mensagem:
        # Outros tipos de atualização (edição de mensagem, sticker, entrada
        # num grupo...) não são o que este bot faz.
        return {"ok": "ignorado"}

    chat_id = mensagem.get("chat", {}).get("id")
    if chat_id != settings.telegram_chat_id:
        return {"ok": "ignorado"}

    quando = datetime.fromtimestamp(mensagem["date"], tz=timezone.utc).date()
    resposta = _processar(db, mensagem["text"], quando)

    await _responder(chat_id, resposta)
    return {"ok": "processado"}


def _processar(db: Session, texto: str, data_envio: date) -> str:
    try:
        pedido = interpretar(texto)
    except ErroInterpretacao as erro:
        return f"⚠️ {erro}"

    ano_ref = db.query(Ano).filter(Ano.ano == data_envio.year).one_or_none()
    if ano_ref is None:
        return (
            f"⚠️ O ano {data_envio.year} ainda não existe no app. "
            "Crie-o por lá antes de lançar por aqui."
        )
    if ano_ref.arquivado:
        return f"⚠️ O ano {data_envio.year} está arquivado (somente leitura)."

    contas = db.query(Conta).filter(Conta.ativa.is_(True)).order_by(Conta.ordem).all()
    if not contas:
        return "⚠️ Nenhuma conta cadastrada ainda. Crie uma pelo app primeiro."

    conta, aviso_conta = escolher_conta(pedido.conta_pedida, contas, contas[0])

    regras = [
        (normalizar(r.padrao), r.categoria) for r in db.query(RegraCategorizacao).all()
    ]
    categoria = sugerir_categoria(pedido.descricao, regras) if pedido.descricao else None

    db.add(
        Lancamento(
            ano_id=ano_ref.id,
            conta_id=conta.id,
            mes=data_envio.month,
            data=data_envio,
            valor=pedido.valor,
            tipo=TipoLancamento.SAIDA,
            categoria_id=categoria.id if categoria else None,
            descricao=pedido.descricao,
        )
    )
    db.commit()

    valor_formatado = f"{pedido.valor:.2f}".replace(".", ",")
    linha = " — ".join(
        [
            f"✅ R$ {valor_formatado}",
            pedido.descricao or "(sem descrição)",
            conta.nome,
            categoria.nome if categoria else "Sem categoria",
            data_envio.strftime("%d/%m/%Y"),
        ]
    )
    if aviso_conta:
        linha += f"\n({aviso_conta})"
    return linha


async def _responder(chat_id: int, texto: str) -> None:
    url = f"{_API_TELEGRAM}/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as cliente:
        await cliente.post(url, json={"chat_id": chat_id, "text": texto})
