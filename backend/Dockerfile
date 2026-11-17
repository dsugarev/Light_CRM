# syntax=docker/dockerfile:1
# Backend image: API (default command), worker (`python -m app.worker`) and
# migrations (`alembic upgrade head`) all run from this one image.

FROM ghcr.io/astral-sh/uv:0.13.4 AS uv

FROM python:3.14.8-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv/backend
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

FROM python:3.14.8-slim-trixie AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 crm && useradd --system --uid 10001 --gid crm --no-create-home crm
COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=root:root /srv/backend /srv/backend
WORKDIR /srv/backend
USER crm
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", \
     "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
