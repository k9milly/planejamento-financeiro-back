# ADR-17 — Limite de tentativas em login, cadastro e recuperação de senha

**Status:** proposto

## Contexto

`POST /auth/login` não tem nenhum limite de tentativas hoje — a revisão de
segurança já apontou isso como risco baixo (sem cadastro aberto, não há
como descobrir e-mails pra atacar), mas o `ADR-16` torna o cadastro público
e a recuperação de senha também pública. As duas coisas juntas mudam a
gravidade: um formulário de cadastro aberto sem limite é convite pra
criação de conta em massa (e cada conta nova de verdade cria um `Espaco`
— ver `ADR-15` — então isso também seria um jeito barato de poluir o
banco); recuperação de senha sem limite permite adivinhar, por tentativa e
erro, quais e-mails têm conta (mesmo respondendo sempre "sucesso", um
atacante mediria a demora da resposta — enviar e-mail é mais lento que só
checar "não existe" — se não houver limite que torne isso caro de medir em
massa).

## Decisão

Um limitador simples, por e-mail **e** por IP, nos três endpoints públicos
(`/auth/login`, `/auth/cadastro`, `/auth/esqueci-senha`):

```python
class TentativaAcesso(Base):
    """Registro de tentativa, pra decidir bloqueio temporário.

    Expurgado por uma rotina simples (ou por consulta que já ignora
    linhas velhas) — não precisa virar histórico permanente.
    """
    __tablename__ = "tentativas_acesso"
    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(255), index=True)   # email normalizado, ou IP
    endpoint: Mapped[str] = mapped_column(String(40))
    em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
LIMITE = 5          # tentativas
JANELA_MINUTOS = 15  # por e-mail E por IP, o que bloquear primeiro vale

def verificar_limite(chave: str, endpoint: str, db: Session) -> None:
    desde = datetime.now(timezone.utc) - timedelta(minutes=JANELA_MINUTOS)
    recentes = db.query(TentativaAcesso).filter(
        TentativaAcesso.chave == chave,
        TentativaAcesso.endpoint == endpoint,
        TentativaAcesso.em >= desde,
    ).count()
    if recentes >= LIMITE:
        raise HTTPException(429, detail="Muitas tentativas. Espere alguns minutos e tente de novo.")

def registrar_tentativa(chave: str, endpoint: str, db: Session) -> None:
    db.add(TentativaAcesso(chave=chave, endpoint=endpoint))
    db.commit()
```

Chamado no início de `login`, `cadastro` e `esqueci_senha`: confere o
limite por e-mail normalizado **e** por IP do pedido (`request.client.host`
— atrás de um proxy como o do Fly, confirmar se chega o IP real ou se
precisa ler `X-Forwarded-For`; isso é um detalhe de implementação a
validar contra o ambiente real, não assumido aqui), registra a tentativa
sempre (sucesso ou falha), nunca revela qual dos dois limites (e-mail ou
IP) foi batido — mesma filosofia de "não vazar informação específica" já
usada na mensagem de erro do login.

**Por que no banco, não em memória:** o Fly pode rodar mais de uma máquina
sob carga (`fly.toml` já permite isso); um limitador em memória por
processo não veria as tentativas que caíram em outra máquina. Uma tabela
simples resolve sem precisar de Redis ou outro serviço novo — o volume de
tentativas de login é baixo o suficiente para uma tabela SQL dar conta
sem índice sofisticado.

## Consequências

- Migração: tabela `tentativas_acesso` nova.
- Os três endpoints (`login`, `cadastro`, `esqueci-senha`) chamam
  `verificar_limite`/`registrar_tentativa` — poucas linhas cada, a lógica
  fica centralizada em `security.py` ou num módulo novo
  `app/limite_acesso.py`.
- Precisa de uma rotina de limpeza (um `DELETE` de linhas mais velhas que
  a janela, rodado ocasionalmente — pode ser tão simples quanto apagar as
  antigas a cada escrita nova, já que o volume é baixo).
- Testes novos: 6ª tentativa errada de login no mesmo e-mail dentro de 15
  minutos responde `429`; esperar a janela passar libera de novo;
  tentativas de IPs diferentes contra e-mails diferentes não se
  bloqueiam entre si indevidamente.

## Alternativas consideradas

- **CAPTCHA.** Rejeitado por agora — adiciona dependência de terceiro
  (reCAPTCHA/hCaptcha) e fricção de uso para resolver um problema que um
  limite de tentativas simples já resolve suficientemente bem no volume de
  uso esperado (uso pessoal/familiar, não um serviço público de massa).
  Pode entrar depois se o cadastro aberto atrair tentativa de abuso real.
- **Bloqueio permanente da conta após N tentativas**, em vez de temporário.
  Rejeitado — um bloqueio permanente por erro de digitação seria uma forma
  fácil de "trancar" a própria conta ou a de outra pessoa de propósito
  (ataque de negação de serviço contra uma conta específica); temporário
  (15 minutos) já desencoraja força bruta sem esse risco.
- **Limitar só por IP, sem considerar o e-mail.** Rejeitada — várias
  pessoas de uma mesma casa/rede (exatamente o caso de uso que motivou o
  `ADR-15`) compartilhariam o mesmo IP em redes residenciais com NAT; só
  por e-mail também não bastaria (um atacante trocando de IP burlaria um
  limite só-por-e-mail se o e-mail não fosse também considerado). Os dois
  juntos cobrem o que cada um sozinho deixaria passar.
