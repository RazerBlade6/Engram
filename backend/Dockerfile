FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

# Extras to install: the worker image passes "--extra ingest" for Docling and PyTorch.
ARG EXTRAS=""

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    FASTEMBED_CACHE_PATH=/models/fastembed

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project $EXTRAS

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev $EXTRAS

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# The same image runs the worker: docker compose overrides the command.
CMD ["uvicorn", "engram.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
