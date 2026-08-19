"""Interpreta mensagens curtas de lançamento rápido, tipo "15, brownie, mercado
pago", enviadas pelo bot do Telegram.

Formato fixo de propósito, sem IA: `valor, descrição, conta`, com descrição e
conta opcionais. O valor é sempre lido **antes** de qualquer divisão por
vírgula — "15,50, brownie" usa a vírgula tanto para separar centavos quanto
para separar campos, e ler o valor primeiro evita que ele seja cortado ao
meio.

A conta é casada por trecho: "cartao credito mercado pago" já reconhece a
conta "Mercado Pago" sem o usuário precisar escrever só o nome dela — é a
mesma ideia das regras de categorização por trecho na descrição.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.services.categorizacao import normalizar

# Âncora o valor no início da mensagem. "R$" antes do número ("R$ 15") e
# "reais" depois ("15 reais") são as duas formas comuns de escrever e são
# descartadas; o resto do texto some para o grupo `resto`.
_PADRAO_VALOR = re.compile(
    r"^\s*(?:r\$\s*)?(?P<valor>\d+(?:[.,]\d{1,2})?)\s*(?:reais?)?\s*,?\s*(?P<resto>.*)$",
    re.IGNORECASE | re.DOTALL,
)


class ErroInterpretacao(ValueError):
    """A mensagem não segue o formato esperado. A string do erro já é a
    resposta a devolver no Telegram."""


@dataclass(frozen=True)
class LancamentoRapido:
    valor: Decimal
    descricao: str
    # Texto bruto do terceiro campo, como o usuário escreveu — ainda não
    # casado com uma conta cadastrada. Fica None se o campo não veio.
    conta_pedida: str | None


def interpretar(texto: str) -> LancamentoRapido:
    bruto = texto.strip()
    if not bruto:
        raise ErroInterpretacao(
            "Mensagem vazia. Formato: valor, descrição, conta "
            "(descrição e conta são opcionais). Ex.: 15, brownie, mercado pago"
        )

    casado = _PADRAO_VALOR.match(bruto)
    if not casado:
        raise ErroInterpretacao(
            f"Não entendi o valor em \"{bruto}\". Comece a mensagem com o "
            "valor, ex.: 15, brownie, mercado pago"
        )

    valor_bruto = casado.group("valor")
    try:
        valor = Decimal(valor_bruto.replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation as erro:
        raise ErroInterpretacao(f"Valor inválido: \"{valor_bruto}\".") from erro
    if valor <= 0:
        raise ErroInterpretacao("O valor precisa ser maior que zero.")

    resto = casado.group("resto").strip()
    campos = [c.strip() for c in resto.split(",", 1)] if resto else []
    descricao = campos[0] if campos and campos[0] else ""
    conta_pedida = campos[1] if len(campos) > 1 and campos[1] else None

    return LancamentoRapido(valor=valor, descricao=descricao, conta_pedida=conta_pedida)


def escolher_conta(conta_pedida, contas, conta_padrao):
    """Casa o texto pedido com uma conta cadastrada, por trecho normalizado.

    `contas` e `conta_padrao` são objetos com atributo `.nome`. Devolve a
    conta escolhida e, quando não reconheceu o pedido e caiu no padrão, um
    aviso em texto para explicar isso na resposta.
    """
    if not conta_pedida:
        return conta_padrao, None

    alvo = normalizar(conta_pedida)
    candidatas = [c for c in contas if normalizar(c.nome) in alvo]
    if not candidatas:
        return conta_padrao, (
            f'não reconheci a conta "{conta_pedida}", usei {conta_padrao.nome}'
        )

    # Em empate (mais de um nome de conta aparece no trecho), o mais
    # específico — o nome mais longo — vence.
    return max(candidatas, key=lambda c: len(c.nome)), None
