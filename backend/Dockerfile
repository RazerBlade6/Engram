FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# The same image runs the worker: docker compose overrides the command.
CMD ["uvicorn", "engram.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
