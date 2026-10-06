# MCP server Pirátské znalostní báze (Streamable HTTP na portu 8765)
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIRATEKB_DB=/app/index/kb.sqlite

WORKDIR /app

COPY server/requirements.txt server/requirements.txt
COPY ingest/requirements.txt ingest/requirements.txt
RUN pip install -r server/requirements.txt -r ingest/requirements.txt

COPY ingest/ ingest/
COPY server/ server/
COPY data/ data/

# Index se staví při buildu image, start kontejneru je pak okamžitý.
RUN python -m server.kb.build

EXPOSE 8765

CMD ["python", "-m", "server", "--http", "--host", "0.0.0.0", "--port", "8765"]
