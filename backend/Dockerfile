# Imagem do backend. Usada pelo Fly.io, mas serve para qualquer host que
# aceite container.

FROM python:3.12-slim

# Impede o Python de gravar .pyc e de bufferizar a saída — sem isto os logs do
# servidor só aparecem quando o buffer enche, atrapalhando diagnosticar erro.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# As dependências vêm antes do código: enquanto o requirements.txt não mudar,
# o Docker reaproveita esta camada e o build fica em segundos.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Roda como usuário comum. Se a aplicação for comprometida, o atacante não
# começa com privilégios de root dentro do container.
RUN useradd --create-home app && chown -R app:app /app
USER app

EXPOSE 8000

# Aplica as migrações e só então sobe. Se a migração falhar, o container morre
# em vez de servir requisições contra um schema errado.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
