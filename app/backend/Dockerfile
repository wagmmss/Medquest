FROM python:3.12-slim

WORKDIR /app
RUN groupadd --system appuser && useradd --system --gid appuser --no-create-home appuser \
    && chown appuser:appuser /app

COPY requirements-web.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r requirements-web.txt

# Keep the large, rarely-changing image corpus in its own layer. A backend code
# change can then publish and download only the small source layers below.
COPY --chown=appuser:appuser static ./static
COPY --chown=appuser:appuser data ./data
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser api ./api
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser *.py ./
COPY --chown=appuser:appuser *.json ./
COPY --chown=appuser:appuser *.txt ./

ENV PORT=8000
ENV PYTHONUNBUFFERED=1
# As DDLs e migrações são executadas uma vez no entrypoint abaixo, nunca por
# cada worker Gunicorn.
ENV MEDQUEST_AUTO_MIGRATE=0
EXPOSE 8000

USER appuser

CMD ["sh", "-c", "python -m scripts.migrate_db && exec gunicorn -w 2 --worker-class gthread --threads 8 --timeout 120 'api:create_app()'"]
