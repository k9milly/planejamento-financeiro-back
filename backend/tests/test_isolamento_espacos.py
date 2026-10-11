"""Dois espaços colidindo de propósito — nenhum dado atravessa (ADR-15).

Este é o teste que o ADR-15 chama de critério de aceite inegociável, e ele
pesa mais do que qualquer outro do projeto: a falha que ele procura não é um
cálculo errado, é o dinheiro de uma família aparecendo para outra.

## Como ele procura a falha

Dois usuários, cada um no seu espaço, com dados que **colidem de propósito**:
os dois têm um "Ano 2026", uma conta "Nubank", uma categoria "Alimentação". Se
alguma unicidade do banco ainda fosse global, este arquivo não passaria da
primeira fixture — foi assim que as cinco restrições globais apareceram.

Além do que colide, cada espaço cria linhas **marcadas**: texto com
`SEGREDO-B` e valores terminados em `777.77`. Aí a verificação vira simples e
genérica: a resposta que o espaço A recebe nunca pode conter uma marca do B.
Tabelas sem campo de texto (saldo inicial, fatura mensal, gasto fixo pago)
entram por essa segunda marca, a numérica.

## Por que varrer as rotas a partir do OpenAPI

`test_toda_rota_de_leitura_esta_coberta` compara a lista varrida com a lista
que o próprio app publica. Uma rota nova entra na varredura ou o teste falha
pedindo que ela entre — a mesma ideia de `modelos_protegidos()` em
`app/espaco.py`: o que protege não pode depender de alguém lembrar.
"""

from __future__ import annotations

import pytest

from app.models import Espaco, MembroEspaco, PapelMembro, Usuario
from app.security import gerar_hash
from tests.conftest import criar_usuario_com_espaco

ANO = 2026

# Rotas de leitura que não falam de dinheiro, logo não entram na varredura.
# Lista curta e explícita de propósito: cada item aqui é uma dispensa que
# alguém precisa justificar.
FORA_DA_VARREDURA = {
    "/saude",  # só diz que o processo está no ar
    "/auth/eu",  # o próprio perfil; não tem dado de espaço nenhum
}


# --------------------------------------------------------------------------- #
# Montagem dos dois espaços
# --------------------------------------------------------------------------- #
def _logar(cliente_sem_login, email, senha):
    """Um cliente novo com o token desta pessoa.

    `TestClient` compartilha cabeçalhos, então os dois espaços não podem usar
    o mesmo objeto — senão o segundo login sobrescreveria o primeiro e o teste
    passaria sem testar nada.
    """
    resposta = cliente_sem_login.post("/auth/login", json={"email": email, "senha": senha})
    assert resposta.status_code == 200, resposta.text
    token = resposta.json()["token"]

    class Sessao:
        """Repassa os métodos do TestClient sempre com este token."""

        def __init__(self, base, token):
            self._base = base
            self._cabecalhos = {"Authorization": f"Bearer {token}"}

        def _chamar(self, metodo, url, **kwargs):
            cabecalhos = dict(self._cabecalhos)
            cabecalhos.update(kwargs.pop("headers", {}) or {})
            return getattr(self._base, metodo)(url, headers=cabecalhos, **kwargs)

        def get(self, url, **kw):
            return self._chamar("get", url, **kw)

        def post(self, url, **kw):
            return self._chamar("post", url, **kw)

        def patch(self, url, **kw):
            return self._chamar("patch", url, **kw)

        def put(self, url, **kw):
            return self._chamar("put", url, **kw)

        def delete(self, url, **kw):
            # `httpx.Client.delete` não aceita corpo; `DELETE /auth/eu` pede a
            # senha no corpo, então a chamada vai pelo `request` genérico.
            cabecalhos = dict(self._cabecalhos)
            cabecalhos.update(kw.pop("headers", {}) or {})
            return self._base.request("DELETE", url, headers=cabecalhos, **kw)

    return Sessao(cliente_sem_login, token)


def _povoar(sessao, marca: str, valor_marcado: str) -> dict:
    """Um espaço com um pouco de cada coisa: o que colide e o que é marcado.

    Devolve os ids criados, que depois servem para montar as URLs da varredura
    — o espaço A vai pedir, uma por uma, as URLs com os ids do B.
    """
    criados: dict[str, int] = {}

    assert sessao.post("/anos", json={"ano": ANO}).status_code == 201

    # --- o que colide: mesmo nome nos dois espaços ------------------------- #
    conta = sessao.post("/contas", json={"nome": "Nubank"}).json()
    categoria = sessao.post("/categorias", json={"nome": "Alimentação"}).json()
    criados["conta_id"] = conta["id"]
    criados["categoria_id"] = categoria["id"]

    # --- o que é marcado: só pode aparecer para quem criou ----------------- #
    cartao = sessao.post(
        "/contas",
        json={
            "nome": f"Cartão {marca}",
            "tipo": "cartao_credito",
            "dia_vencimento_fatura": 10,
        },
    ).json()
    criados["cartao_id"] = cartao["id"]

    lancamento = sessao.post(
        f"/anos/{ANO}/lancamentos",
        json={
            "mes": 3,
            "data": f"{ANO}-03-05",
            "valor": valor_marcado,
            "tipo": "saida",
            "descricao": f"Mercado {marca}",
            "conta_id": conta["id"],
            "categoria_id": categoria["id"],
        },
    )
    assert lancamento.status_code == 201, lancamento.text
    criados["lancamento_id"] = lancamento.json()["id"]

    gasto = sessao.post(
        f"/anos/{ANO}/gastos-fixos",
        json={
            "descricao": f"Internet {marca}",
            "valor": valor_marcado,
            "dia_vencimento": 10,
            "conta_id": conta["id"],
        },
    )
    assert gasto.status_code == 201, gasto.text
    criados["gasto_id"] = gasto.json()["id"]
    # Marca também `gastos_fixos_mensais`, que não tem campo de texto.
    sessao.post(f"/anos/{ANO}/gastos-fixos/{criados['gasto_id']}/meses/3/pagar")

    # `saldos_iniciais`: sem texto, entra pela marca numérica.
    sessao.put(
        f"/anos/{ANO}/saldos-iniciais",
        json=[{"conta_id": conta["id"], "saldo": valor_marcado, "guardado": "0"}],
    )

    caixinha = sessao.post(
        f"/contas/{conta['id']}/caixinhas", json={"nome": f"Reserva {marca}"}
    )
    assert caixinha.status_code == 201, caixinha.text
    criados["caixinha_id"] = caixinha.json()["id"]

    item = sessao.post(
        f"/anos/{ANO}/wishlist",
        json={"desejo": f"Fone {marca}", "valor": valor_marcado, "somar": True},
    )
    assert item.status_code == 201, item.text
    criados["item_id"] = item.json()["id"]

    meta = sessao.post(
        "/metas-poupanca",
        json={"tipo": "mensal", "nome": f"Meta {marca}", "valor_alvo": valor_marcado},
    )
    assert meta.status_code == 201, meta.text
    criados["meta_id"] = meta.json()["id"]

    regra = sessao.post(
        "/regras", json={"padrao": f"padrao {marca}", "categoria_id": categoria["id"]}
    )
    assert regra.status_code == 201, regra.text
    criados["regra_id"] = regra.json()["id"]

    compra = sessao.post(
        f"/anos/{ANO}/compras-parceladas",
        json={
            "descricao": f"Tênis {marca}",
            "conta_id": cartao["id"],
            "data_primeira_parcela": f"{ANO}-03-10",
            "numero_parcelas": 3,
            "tem_juros": False,
            "valor_total": valor_marcado,
        },
    )
    assert compra.status_code == 201, compra.text
    criados["compra_id"] = compra.json()["id"]

    # `faturas_mensais`: criada ao pagar a fatura do cartão. A conta de
    # pagamento é obrigatória quando o cartão não tem uma padrão.
    paga = sessao.post(
        f"/anos/{ANO}/cartoes/{cartao['id']}/fatura/3/pagar",
        json={"conta_pagamento_id": conta["id"]},
    )
    assert paga.status_code in (200, 201), paga.text

    # `cores_forma_pagamento`: a tabela cuja chave primária era a forma de
    # pagamento, e que portanto daria uma cor só para o sistema inteiro.
    sessao.put("/preferencias/cores-forma-pagamento/credito", json={"cor": "#aabb77"})

    return criados


@pytest.fixture()
def dois_espacos(cliente_sem_login, sessao_teste):
    """Espaço A e espaço B, cada um com seu dono, dados colidindo.

    A fixture em si já é uma asserção: se alguma unicidade do banco ainda
    fosse global (`anos.ano`, `contas.nome`, `categorias.nome`,
    `regras_categorizacao.padrao`, a chave de `cores_forma_pagamento`), o
    segundo `_povoar` quebraria aqui com erro de restrição.
    """
    db = sessao_teste()
    try:
        criar_usuario_com_espaco(db, "a@exemplo.com", "senha-a-12345", "Espaço A")
        criar_usuario_com_espaco(db, "b@exemplo.com", "senha-b-12345", "Espaço B")
    finally:
        db.close()

    sessao_a = _logar(cliente_sem_login, "a@exemplo.com", "senha-a-12345")
    sessao_b = _logar(cliente_sem_login, "b@exemplo.com", "senha-b-12345")

    ids_a = _povoar(sessao_a, "SEGREDO-A", "111.11")
    ids_b = _povoar(sessao_b, "SEGREDO-B", "777.77")

    return {
        "a": sessao_a,
        "b": sessao_b,
        "base": cliente_sem_login,
        "ids_a": ids_a,
        "ids_b": ids_b,
    }


def _urls_de_leitura(ids: dict) -> list[str]:
    """Toda rota de leitura do sistema, montada com os ids de um espaço."""
    return [
        "/alertas",
        "/anos",
        f"/anos/{ANO}/cartoes/{ids['cartao_id']}/fatura/3",
        f"/anos/{ANO}/gastos-fixos",
        f"/anos/{ANO}/lancamentos",
        f"/anos/{ANO}/resumo",
        f"/anos/{ANO}/wishlist",
        f"/anos/{ANO}/wishlist/total",
        "/categorias",
        f"/contas/{ids['conta_id']}/caixinhas",
        "/contas",
        "/metas-poupanca",
        "/metas-poupanca/ativas",
        "/preferencias/cores-forma-pagamento",
        "/preferencias/layout-dashboard",
        "/regras",
    ]


# Os moldes correspondentes, para conferir contra o OpenAPI que nada ficou de
# fora. Mantidos ao lado da lista acima porque é a dupla que precisa andar
# junto quando uma rota nova nasce.
MOLDES_VARRIDOS = {
    "/alertas",
    "/anos",
    "/anos/{ano}/cartoes/{cartao_id}/fatura/{mes}",
    "/anos/{ano}/gastos-fixos",
    "/anos/{ano}/lancamentos",
    "/anos/{ano}/resumo",
    "/anos/{ano}/wishlist",
    "/anos/{ano}/wishlist/total",
    "/categorias",
    "/contas",
    "/contas/{conta_id}/caixinhas",
    "/espacos/{espaco_id}",
    "/espacos/{espaco_id}/exportar",
    "/espacos/{espaco_id}/membros",
    "/metas-poupanca",
    "/metas-poupanca/ativas",
    "/preferencias/cores-forma-pagamento",
    "/preferencias/layout-dashboard",
    "/regras",
}


class TestVarreduraDeLeitura:
    def test_toda_rota_de_leitura_esta_coberta(self):
        """Rota de leitura nova entra na varredura, ou este teste falha.

        Sem esta conferência, criar um endpoint e esquecer de incluí-lo aqui
        deixaria um caminho sem nenhum teste de isolamento — e seria um
        esquecimento silencioso, que é exatamente o modo de falha que o ADR-15
        existe para fechar.
        """
        from app.main import app

        caminhos = app.openapi()["paths"]
        publicadas = {p for p in caminhos if "get" in caminhos[p]} - FORA_DA_VARREDURA

        faltando = publicadas - MOLDES_VARRIDOS
        assert not faltando, (
            "Rotas de leitura sem teste de isolamento: "
            f"{sorted(faltando)}. Inclua em `_urls_de_leitura`/`MOLDES_VARRIDOS` "
            "ou justifique em `FORA_DA_VARREDURA`."
        )

        sobrando = MOLDES_VARRIDOS - publicadas
        assert not sobrando, f"Rotas varridas que não existem mais: {sorted(sobrando)}"

    def test_espaco_a_nao_ve_nada_do_b(self, dois_espacos):
        """A varredura em si: nenhuma marca do B na resposta que o A recebe."""
        sessao_a = dois_espacos["a"]

        for url in _urls_de_leitura(dois_espacos["ids_b"]):
            resposta = sessao_a.get(url)
            texto = resposta.text
            assert "SEGREDO-B" not in texto, f"{url} vazou texto do espaço B"
            assert "777.77" not in texto, f"{url} vazou valor do espaço B"

    def test_espaco_b_nao_ve_nada_do_a(self, dois_espacos):
        """O mesmo na direção contrária.

        Não é redundante: um filtro que comparasse `espaco_id` com o id errado
        (o do outro, ou um fixo) poderia passar numa direção e falhar na outra.
        """
        sessao_b = dois_espacos["b"]

        for url in _urls_de_leitura(dois_espacos["ids_a"]):
            resposta = sessao_b.get(url)
            assert "SEGREDO-A" not in resposta.text, f"{url} vazou texto do espaço A"
            assert "111.11" not in resposta.text, f"{url} vazou valor do espaço A"

    def test_cada_espaco_continua_vendo_o_proprio_dado(self, dois_espacos):
        """O contrapeso: um filtro que esconde tudo passaria nos dois acima.

        Sem este teste, `espaco_id = -1` para todo mundo seria uma
        "correção" aprovada.
        """
        sessao_b = dois_espacos["b"]

        for url in _urls_de_leitura(dois_espacos["ids_b"]):
            assert sessao_b.get(url).status_code == 200, url

        assert "SEGREDO-B" in sessao_b.get(f"/anos/{ANO}/lancamentos").text
        assert "SEGREDO-B" in sessao_b.get("/contas").text
        assert "SEGREDO-B" in sessao_b.get(f"/anos/{ANO}/wishlist").text
        assert "SEGREDO-B" in sessao_b.get("/metas-poupanca").text
        assert "SEGREDO-B" in sessao_b.get("/regras").text
        assert "SEGREDO-B" in sessao_b.get(
            f"/contas/{dois_espacos['ids_b']['conta_id']}/caixinhas"
        ).text


class TestEscritaCruzada:
    """Ler não é o único jeito de atravessar: editar e apagar também."""

    def test_nao_edita_lancamento_do_outro(self, dois_espacos):
        sessao_a, ids_b = dois_espacos["a"], dois_espacos["ids_b"]
        resposta = sessao_a.patch(
            f"/anos/{ANO}/lancamentos/{ids_b['lancamento_id']}",
            json={"descricao": "invadido"},
        )
        assert resposta.status_code == 404, resposta.text
        # 404 por si não basta: o PATCH poderia ter gravado antes de falhar na
        # leitura de volta. Quem confirma é o dono do dado.
        assert "invadido" not in dois_espacos["b"].get(f"/anos/{ANO}/lancamentos").text

    def test_nao_apaga_lancamento_do_outro(self, dois_espacos):
        sessao_a, sessao_b = dois_espacos["a"], dois_espacos["b"]
        alvo = dois_espacos["ids_b"]["lancamento_id"]

        assert sessao_a.delete(f"/anos/{ANO}/lancamentos/{alvo}").status_code == 404
        assert "SEGREDO-B" in sessao_b.get(f"/anos/{ANO}/lancamentos").text

    @pytest.mark.parametrize(
        "molde",
        [
            "/contas/{id}",
            "/categorias/{id}",
            "/anos/2026/wishlist/{id}",
        ],
    )
    def test_nao_edita_outros_registros_do_outro(self, dois_espacos, molde):
        sessao_a, ids_b = dois_espacos["a"], dois_espacos["ids_b"]
        alvo = {
            "/contas/{id}": ids_b["conta_id"],
            "/categorias/{id}": ids_b["categoria_id"],
            "/anos/2026/wishlist/{id}": ids_b["item_id"],
        }[molde]

        resposta = sessao_a.patch(molde.format(id=alvo), json={"nome": "invadido"})
        assert resposta.status_code == 404, resposta.text

    def test_nao_apaga_caixinha_do_outro(self, dois_espacos):
        sessao_a, ids_b = dois_espacos["a"], dois_espacos["ids_b"]
        url = f"/contas/{ids_b['conta_id']}/caixinhas/{ids_b['caixinha_id']}"
        assert sessao_a.delete(url).status_code == 404

    def test_nao_apaga_meta_do_outro(self, dois_espacos):
        sessao_a, ids_b = dois_espacos["a"], dois_espacos["ids_b"]
        assert sessao_a.delete(f"/metas-poupanca/{ids_b['meta_id']}").status_code == 404

    def test_nao_apaga_regra_do_outro(self, dois_espacos):
        sessao_a, ids_b = dois_espacos["a"], dois_espacos["ids_b"]
        assert sessao_a.delete(f"/regras/{ids_b['regra_id']}").status_code == 404

    def test_lancamento_criado_nasce_no_espaco_de_quem_criou(
        self, dois_espacos, sessao_teste
    ):
        """O carimbo de `before_flush`, visto do banco.

        Conferir pela API não provaria nada: se o carimbo errasse o espaço, a
        leitura erraria do mesmo jeito e as duas pontas combinariam.
        """
        sessao_a, ids_a = dois_espacos["a"], dois_espacos["ids_a"]
        criado = sessao_a.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "mes": 4,
                "data": f"{ANO}-04-01",
                "valor": "10.00",
                "tipo": "entrada",
                "descricao": "carimbo",
                "conta_id": ids_a["conta_id"],
            },
        )
        assert criado.status_code == 201, criado.text

        from app.models import Lancamento

        db = sessao_teste()
        try:
            # Sessão crua, sem espaço fixado: vê as duas famílias de uma vez.
            linha = db.get(Lancamento, criado.json()["id"])
            dono = db.query(Usuario).filter(Usuario.email == "a@exemplo.com").one()
            assert linha.espaco_id == dono.espaco_atual_id
        finally:
            db.close()

    def test_espaco_id_no_corpo_nao_move_registro(self, dois_espacos, sessao_teste):
        """`espaco_id` no JSON é ignorado, não obedecido (regra de schema do ADR-15).

        Era o buraco óbvio: se um `*Criar` aceitasse o campo, bastaria um
        `POST` com o id alheio para plantar dado no espaço de outra pessoa.
        """
        sessao_a, ids_a = dois_espacos["a"], dois_espacos["ids_a"]
        db = sessao_teste()
        try:
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
        finally:
            db.close()

        criado = sessao_a.post(
            f"/anos/{ANO}/lancamentos",
            json={
                "mes": 4,
                "data": f"{ANO}-04-02",
                "valor": "10.00",
                "tipo": "entrada",
                "descricao": "forjado",
                "conta_id": ids_a["conta_id"],
                "espaco_id": espaco_b,
            },
        )
        assert criado.status_code == 201, criado.text
        assert "forjado" not in dois_espacos["b"].get(f"/anos/{ANO}/lancamentos").text


class TestEspacoAtual:
    def test_sem_espaco_escolhido_nao_ve_nada(self, dois_espacos, sessao_teste):
        """Usuário autenticado e sem espaço: tudo vazio, nunca tudo visível.

        É o caso que o sentinela `SEM_ESPACO` existe para cobrir. Com `None` em
        vez dele, o filtro se desligaria e esta pessoa veria os dois espaços.
        """
        db = sessao_teste()
        try:
            pessoa = db.query(Usuario).filter(Usuario.email == "a@exemplo.com").one()
            pessoa.espaco_atual_id = None
            db.commit()
        finally:
            db.close()

        sessao_a = dois_espacos["a"]
        assert sessao_a.get("/contas").json() == []
        assert sessao_a.get("/anos").json() == []
        assert sessao_a.get("/categorias").json() == []
        assert sessao_a.get(f"/anos/{ANO}/lancamentos").status_code == 404

        eu = sessao_a.get("/auth/eu").json()
        assert eu["espaco_atual_id"] is None

    def test_trocar_para_espaco_que_nao_e_meu_recusa(self, dois_espacos, sessao_teste):
        db = sessao_teste()
        try:
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
        finally:
            db.close()

        resposta = dois_espacos["a"].patch(
            "/auth/espaco-atual", json={"espaco_id": espaco_b}
        )
        assert resposta.status_code == 422
        assert "não participa" in resposta.json()["detail"]

    def test_trocar_para_espaco_inexistente_recusa(self, dois_espacos):
        resposta = dois_espacos["a"].patch("/auth/espaco-atual", json={"espaco_id": 9999})
        assert resposta.status_code == 422

    def test_quem_participa_dos_dois_ve_um_de_cada_vez(self, dois_espacos, sessao_teste):
        """O caso que motivou o ADR: duas pessoas, um espaço — e a troca.

        A entra no espaço do B (o convite é o ADR-16; aqui o vínculo é escrito
        direto no banco). O que importa é que depois da troca ela vê **só** o B
        — não os dois somados.
        """
        db = sessao_teste()
        try:
            pessoa_a = db.query(Usuario).filter(Usuario.email == "a@exemplo.com").one()
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one()
            db.add(
                MembroEspaco(
                    espaco_id=espaco_b.id,
                    usuario_id=pessoa_a.id,
                    papel=PapelMembro.MEMBRO,
                )
            )
            db.commit()
            id_b = espaco_b.id
        finally:
            db.close()

        sessao_a = dois_espacos["a"]

        # Antes da troca, o espaço do B já aparece no seletor — e os dados,
        # não.
        eu = sessao_a.get("/auth/eu").json()
        assert {e["nome"] for e in eu["espacos"]} == {"Espaço A", "Espaço B"}
        assert "SEGREDO-B" not in sessao_a.get("/contas").text

        trocado = sessao_a.patch("/auth/espaco-atual", json={"espaco_id": id_b})
        assert trocado.status_code == 200, trocado.text
        assert trocado.json()["espaco_atual_id"] == id_b

        contas = sessao_a.get("/contas").text
        assert "SEGREDO-B" in contas
        assert "SEGREDO-A" not in contas


class TestRotasDoEspaco:
    def test_nao_detalha_espaco_alheio(self, dois_espacos, sessao_teste):
        db = sessao_teste()
        try:
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
        finally:
            db.close()

        resposta = dois_espacos["a"].get(f"/espacos/{espaco_b}")
        # 404 e não 403: um 403 confirmaria que o id existe.
        assert resposta.status_code == 404

    def test_nao_exporta_espaco_alheio(self, dois_espacos, sessao_teste):
        db = sessao_teste()
        try:
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
        finally:
            db.close()

        assert dois_espacos["a"].get(f"/espacos/{espaco_b}/exportar").status_code == 404

    def test_exportacao_traz_o_proprio_espaco_inteiro(self, dois_espacos, sessao_teste):
        db = sessao_teste()
        try:
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
        finally:
            db.close()

        resposta = dois_espacos["b"].get(f"/espacos/{espaco_b}/exportar")
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()

        assert corpo["espaco"]["nome"] == "Espaço B"
        assert [m["email"] for m in corpo["membros"]] == ["b@exemplo.com"]

        # Todas as catorze tabelas de dinheiro aparecem, e nenhuma vazia:
        # `_povoar` criou linha em cada uma.
        from app.espaco import modelos_protegidos

        esperadas = {m.__tablename__ for m in modelos_protegidos()}
        assert set(corpo["dados"]) == esperadas
        vazias = [nome for nome, linhas in corpo["dados"].items() if not linhas]
        assert not vazias, f"tabelas sem linha na exportação: {vazias}"

        # Dinheiro sai como string, não float.
        assert corpo["dados"]["lancamentos"][0]["valor"] == "777.77"

        assert "SEGREDO-A" not in resposta.text

    def test_exportar_espaco_que_nao_e_o_ativo(self, dois_espacos, sessao_teste):
        """A armadilha da exportação: espaço pedido ≠ espaço ativo.

        Sem refixar a sessão, a rota devolveria os dados do espaço **ativo**
        com o nome do pedido no cabeçalho — um arquivo plausível e errado. É o
        tipo de engano que o filtro automático produz sem reclamar, e o motivo
        de `exportar()` chamar `fixar_espaco` de novo.
        """
        db = sessao_teste()
        try:
            pessoa_a = db.query(Usuario).filter(Usuario.email == "a@exemplo.com").one()
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one()
            db.add(
                MembroEspaco(
                    espaco_id=espaco_b.id,
                    usuario_id=pessoa_a.id,
                    papel=PapelMembro.MEMBRO,
                )
            )
            db.commit()
            id_b = espaco_b.id
        finally:
            db.close()

        # A continua com o espaço A ativo, e pede a exportação do B.
        corpo = dois_espacos["a"].get(f"/espacos/{id_b}/exportar").json()

        assert corpo["espaco"]["nome"] == "Espaço B"
        descricoes = [l["descricao"] for l in corpo["dados"]["lancamentos"]]
        assert any("SEGREDO-B" in d for d in descricoes)
        assert not any("SEGREDO-A" in d for d in descricoes)

    def test_renomear_exige_ser_dono(self, dois_espacos, sessao_teste):
        db = sessao_teste()
        try:
            pessoa_a = db.query(Usuario).filter(Usuario.email == "a@exemplo.com").one()
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one()
            db.add(
                MembroEspaco(
                    espaco_id=espaco_b.id,
                    usuario_id=pessoa_a.id,
                    papel=PapelMembro.MEMBRO,
                )
            )
            db.commit()
            id_b = espaco_b.id
        finally:
            db.close()

        recusado = dois_espacos["a"].patch(f"/espacos/{id_b}", json={"nome": "meu agora"})
        assert recusado.status_code == 403

        aceito = dois_espacos["b"].patch(f"/espacos/{id_b}", json={"nome": "Casa"})
        assert aceito.status_code == 200
        assert aceito.json()["nome"] == "Casa"


class TestApagarAPropriaConta:
    def _espaco_de(self, sessao_teste, email):
        db = sessao_teste()
        try:
            return db.query(Usuario).filter(Usuario.email == email).one().espaco_atual_id
        finally:
            db.close()

    def test_senha_errada_nao_apaga(self, dois_espacos):
        resposta = dois_espacos["a"].delete("/auth/eu", json={"senha": "errada"})
        assert resposta.status_code == 401
        assert dois_espacos["a"].get("/auth/eu").status_code == 200

    def test_dona_sozinha_apaga_tudo(self, dois_espacos, sessao_teste):
        """Direito ao esquecimento: o espaço e os dados vão junto, de verdade."""
        from app.models import Lancamento

        id_a = self._espaco_de(sessao_teste, "a@exemplo.com")

        resposta = dois_espacos["a"].delete("/auth/eu", json={"senha": "senha-a-12345"})
        assert resposta.status_code == 204, resposta.text

        db = sessao_teste()
        try:
            assert db.get(Espaco, id_a) is None
            assert (
                db.query(Usuario).filter(Usuario.email == "a@exemplo.com").one_or_none()
                is None
            )
            # O CASCADE levou os dados; nada de linha órfã apontando para um
            # espaço que não existe mais.
            restantes = (
                db.query(Lancamento).filter(Lancamento.espaco_id == id_a).count()
            )
            assert restantes == 0
        finally:
            db.close()

        # E o espaço B segue inteiro.
        assert "SEGREDO-B" in dois_espacos["b"].get(f"/anos/{ANO}/lancamentos").text

    def test_dona_com_outro_membro_dentro_recusa(self, dois_espacos, sessao_teste):
        """O espaço não pode ser apagado por baixo dos pés de quem ainda o usa."""
        db = sessao_teste()
        try:
            pessoa_b = db.query(Usuario).filter(Usuario.email == "b@exemplo.com").one()
            id_a = (
                db.query(Usuario).filter(Usuario.email == "a@exemplo.com").one()
            ).espaco_atual_id
            db.add(
                MembroEspaco(
                    espaco_id=id_a, usuario_id=pessoa_b.id, papel=PapelMembro.MEMBRO
                )
            )
            db.commit()
        finally:
            db.close()

        resposta = dois_espacos["a"].delete("/auth/eu", json={"senha": "senha-a-12345"})
        assert resposta.status_code == 409
        assert "responsável pelo espaço" in resposta.json()["detail"]
        assert dois_espacos["a"].get("/auth/eu").status_code == 200

    def test_so_membro_sai_e_o_espaco_fica(self, dois_espacos, sessao_teste):
        """Quem era só convidado apaga a própria conta e os dados ficam."""
        db = sessao_teste()
        try:
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
            convidada = Usuario(
                email="c@exemplo.com",
                senha_hash=gerar_hash("senha-c-12345"),
                espaco_atual_id=espaco_b,
            )
            db.add(convidada)
            db.flush()
            db.add(
                MembroEspaco(
                    espaco_id=espaco_b,
                    usuario_id=convidada.id,
                    papel=PapelMembro.MEMBRO,
                )
            )
            db.commit()
        finally:
            db.close()

        sessao_c = _logar(dois_espacos["base"], "c@exemplo.com", "senha-c-12345")
        assert "SEGREDO-B" in sessao_c.get("/contas").text

        assert sessao_c.delete("/auth/eu", json={"senha": "senha-c-12345"}).status_code == 204

        db = sessao_teste()
        try:
            assert db.get(Espaco, espaco_b) is not None
            assert (
                db.query(Usuario).filter(Usuario.email == "c@exemplo.com").one_or_none()
                is None
            )
        finally:
            db.close()

        assert "SEGREDO-B" in dois_espacos["b"].get("/contas").text


class TestRemoverMembro:
    def _convidar(self, sessao_teste, email_convidado, nome_espaco, papel):
        db = sessao_teste()
        try:
            pessoa = db.query(Usuario).filter(Usuario.email == email_convidado).one()
            espaco = db.query(Espaco).filter(Espaco.nome == nome_espaco).one()
            db.add(
                MembroEspaco(
                    espaco_id=espaco.id, usuario_id=pessoa.id, papel=papel
                )
            )
            db.commit()
            return espaco.id, pessoa.id
        finally:
            db.close()

    def test_dono_remove_membro(self, dois_espacos, sessao_teste):
        id_b, id_pessoa_a = self._convidar(
            sessao_teste, "a@exemplo.com", "Espaço B", PapelMembro.MEMBRO
        )

        resposta = dois_espacos["b"].delete(f"/espacos/{id_b}/membros/{id_pessoa_a}")
        assert resposta.status_code == 204, resposta.text

        # Quem saiu não fica logado vendo um espaço que não é mais dela.
        sessao_a = dois_espacos["a"]
        assert {e["nome"] for e in sessao_a.get("/auth/eu").json()["espacos"]} == {
            "Espaço A"
        }

    def test_membro_nao_remove_outra_pessoa(self, dois_espacos, sessao_teste):
        id_b, _ = self._convidar(
            sessao_teste, "a@exemplo.com", "Espaço B", PapelMembro.MEMBRO
        )
        db = sessao_teste()
        try:
            id_dono = db.query(Usuario).filter(Usuario.email == "b@exemplo.com").one().id
        finally:
            db.close()

        resposta = dois_espacos["a"].delete(f"/espacos/{id_b}/membros/{id_dono}")
        assert resposta.status_code == 403
        assert dois_espacos["b"].get(f"/espacos/{id_b}").status_code == 200

    def test_membro_nao_sai_sozinho(self, dois_espacos, sessao_teste):
        """Lacuna de contrato, registrada e não inventada.

        A especificação diz que remover membro é "só dono", então sair por
        iniciativa própria não tem rota. O teste existe para fixar o
        comportamento atual: se um dia nascer o "sair do espaço", é este
        teste que precisa mudar de lado, de propósito e não por acidente.
        """
        id_b, id_pessoa_a = self._convidar(
            sessao_teste, "a@exemplo.com", "Espaço B", PapelMembro.MEMBRO
        )
        sessao_a = dois_espacos["a"]

        resposta = sessao_a.delete(f"/espacos/{id_b}/membros/{id_pessoa_a}")
        assert resposta.status_code == 403
        assert {e["nome"] for e in sessao_a.get("/auth/eu").json()["espacos"]} == {
            "Espaço A",
            "Espaço B",
        }

    def test_membro_removido_perde_o_espaco_ativo(self, dois_espacos, sessao_teste):
        """Quem é removido não fica logado vendo o espaço de que saiu."""
        id_b, id_pessoa_a = self._convidar(
            sessao_teste, "a@exemplo.com", "Espaço B", PapelMembro.MEMBRO
        )
        sessao_a = dois_espacos["a"]
        assert (
            sessao_a.patch("/auth/espaco-atual", json={"espaco_id": id_b}).status_code
            == 200
        )
        assert "SEGREDO-B" in sessao_a.get("/contas").text

        assert (
            dois_espacos["b"].delete(f"/espacos/{id_b}/membros/{id_pessoa_a}").status_code
            == 204
        )

        eu = sessao_a.get("/auth/eu").json()
        assert eu["espaco_atual_id"] is None
        assert sessao_a.get("/contas").json() == []

    def test_dono_nao_pode_ser_removido(self, dois_espacos, sessao_teste):
        db = sessao_teste()
        try:
            espaco_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
            id_dono = db.query(Usuario).filter(Usuario.email == "b@exemplo.com").one().id
        finally:
            db.close()

        resposta = dois_espacos["b"].delete(f"/espacos/{espaco_b}/membros/{id_dono}")
        assert resposta.status_code == 409


class TestColisaoDeDados:
    def test_os_dois_espacos_tem_o_mesmo_ano_conta_e_categoria(self, dois_espacos):
        """O que as unicidades globais impediam.

        Antes do ADR-15, `anos.ano`, `contas.nome`, `categorias.nome`,
        `regras_categorizacao.padrao` e a chave de `cores_forma_pagamento`
        eram únicos no sistema inteiro — então o segundo espaço a tentar
        "2026" ou "Nubank" recebia 409. O próprio critério de aceite do ADR
        era impossível de escrever.
        """
        for lado in ("a", "b"):
            sessao = dois_espacos[lado]
            assert [a["ano"] for a in sessao.get("/anos").json()] == [ANO]
            assert "Nubank" in {c["nome"] for c in sessao.get("/contas").json()}
            assert "Alimentação" in {
                c["nome"] for c in sessao.get("/categorias").json()
            }

        cores_a = dois_espacos["a"].get("/preferencias/cores-forma-pagamento").json()
        cores_b = dois_espacos["b"].get("/preferencias/cores-forma-pagamento").json()
        assert cores_a and cores_b


class TestFiltroDaSessao:
    """O mecanismo em si, tabela por tabela — e não através das rotas.

    Esta classe nasceu de um teste de mutação que passou e não deveria: com o
    filtro de leitura **desligado** para `lancamentos`, toda a varredura de
    rotas acima continuou verde. O motivo é a proteção transitiva — as rotas
    de lançamento pedem `/anos/2026/...`, e o lançamento do outro espaço fica
    de fora porque pertence ao `Ano` do outro espaço, não porque o filtro
    funcionou.

    Ou seja: a varredura de rotas prova que o sistema **de hoje** não vaza, e
    não que o filtro está no lugar. Quem prova isso é o teste abaixo, que
    consulta cada uma das catorze tabelas direto, sem passar por `ano_id`. A
    diferença importa no dia em que nascer uma rota que não escopa por ano —
    `metas_poupanca.ativas()` já é uma delas.
    """

    def test_toda_tabela_protegida_so_devolve_o_espaco_fixado(
        self, dois_espacos, sessao_teste
    ):
        from app.espaco import fixar_espaco, modelos_protegidos

        db = sessao_teste()
        try:
            id_a = db.query(Espaco).filter(Espaco.nome == "Espaço A").one().id
            id_b = db.query(Espaco).filter(Espaco.nome == "Espaço B").one().id
        finally:
            db.close()

        for espaco_visto, espaco_oculto in ((id_a, id_b), (id_b, id_a)):
            db = sessao_teste()
            try:
                fixar_espaco(db, espaco_visto)
                for modelo in modelos_protegidos():
                    linhas = db.query(modelo).all()
                    assert linhas, (
                        f"{modelo.__tablename__} veio vazia — o teste não "
                        "prova nada sobre uma tabela sem linhas"
                    )
                    alheias = [l for l in linhas if l.espaco_id == espaco_oculto]
                    assert not alheias, (
                        f"{modelo.__tablename__} devolveu "
                        f"{len(alheias)} linha(s) do espaço {espaco_oculto} "
                        f"numa sessão fixada em {espaco_visto}"
                    )
            finally:
                db.close()

    def test_busca_por_chave_primaria_tambem_e_filtrada(
        self, dois_espacos, sessao_teste
    ):
        """`db.get()` entra no filtro — e metade dos routers depende disso.

        Vale ter escrito: `db.get` é o único jeito de ler que poderia atalhar
        o filtro, porque consulta por chave primária e pode responder do mapa
        de identidade sem ir ao banco. Conferido: com a sessão fixada antes da
        primeira leitura (que é o que `usuario_atual` garante), ele filtra.
        """
        from app.espaco import fixar_espaco
        from app.models import Conta

        db = sessao_teste()
        try:
            id_a = db.query(Espaco).filter(Espaco.nome == "Espaço A").one().id
            conta_de_b = (
                db.query(Conta).filter(Conta.espaco_id != id_a).first()
            )
            alvo = conta_de_b.id
        finally:
            db.close()

        db = sessao_teste()
        try:
            fixar_espaco(db, id_a)
            assert db.get(Conta, alvo) is None
        finally:
            db.close()

    def test_sem_espaco_na_sessao_o_sentinela_esconde_tudo(
        self, dois_espacos, sessao_teste
    ):
        from app.espaco import SEM_ESPACO, fixar_espaco
        from app.models import Conta

        db = sessao_teste()
        try:
            fixar_espaco(db, SEM_ESPACO)
            assert db.query(Conta).all() == []
        finally:
            db.close()

    def test_linha_nova_sem_espaco_herda_o_da_sessao(self, dois_espacos, sessao_teste):
        """O carimbo de `before_flush`, direto.

        Sem ele, todo `criar()` de todo router precisaria preencher o campo na
        mão — a disciplina que este módulo existe para não exigir.
        """
        from app.espaco import fixar_espaco
        from app.models import Categoria

        db = sessao_teste()
        try:
            id_a = db.query(Espaco).filter(Espaco.nome == "Espaço A").one().id
        finally:
            db.close()

        db = sessao_teste()
        try:
            fixar_espaco(db, id_a)
            nova = Categoria(nome="Sem espaço informado")
            db.add(nova)
            db.commit()
            assert nova.espaco_id == id_a
        finally:
            db.close()
