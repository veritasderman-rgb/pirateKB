# MCP server Pirátské znalostní báze (Streamable HTTP na /mcp, port z env PORT, výchozí 8765)
# Vercel buildí image z tohoto souboru (vercel.json → services).
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
COPY content/ content/

# Index se staví při buildu image, start kontejneru je pak okamžitý.
RUN python -m server.kb.build

EXPOSE 8765

# Vercel a podobné platformy předávají port v env PORT; lokálně/compose zůstává 8765.
CMD ["sh", "-c", "python -m server --http --host 0.0.0.0 --port ${PORT:-8765}"]
