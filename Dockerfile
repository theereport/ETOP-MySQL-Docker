# Build from the REPO ROOT, not backend/:
#   docker build -f Dockerfile -t etop-backend .
#
# backend/core/config.py resolves PlatformSettings.data_root as two levels
# above backend/core/config.py - i.e. a "data/" directory that is a SIBLING
# of backend/, not backend/data/. Every module that stores uploads, the
# vector store, or training data depends on that sibling layout, so this
# image preserves it exactly: /app/backend and /app/data side by side.

FROM python:3.13-slim-bookworm

# tesseract-ocr is a real runtime dependency (modules/document_intelligence/
# ocr_engine.py shells out to the `tesseract` binary via pytesseract), not
# just a dev tool.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies before copying the rest of the source so this layer
# stays cached across ordinary code changes.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ /app/backend/
COPY data/ /app/data/

# Fixed UID/GID (1000) rather than a dynamically-assigned system one, so the
# bind-mounted host directories in docker-compose.yml can be given matching
# ownership up front (see DEPLOYMENT.md) instead of guessing it after the
# fact.
RUN groupadd --gid 1000 etop && useradd --uid 1000 --gid etop --home /app etop \
    && chown -R etop:etop /app
USER etop

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
