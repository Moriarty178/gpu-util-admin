# API GĐ2: cùng code GĐ1 (FastAPI + gpu_core), driver PostgreSQL (nhóm `pg`). Build từ gốc repo:
#   docker build -f docker/api.Dockerfile .
FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv

ARG WITH_DEV=0
ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN if [ "$WITH_DEV" = "1" ]; then uv sync --frozen --extra pg; else uv sync --frozen --no-dev --extra pg; fi

COPY backend/ ./
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint
RUN chmod +x /usr/local/bin/api-entrypoint \
 && useradd --system --uid 10001 --home /srv app \
 && mkdir -p /data/uploads && chown -R app /data

USER app
EXPOSE 8000
# Migrate + seed (idempotent) rồi mới chạy lệnh chính. 1 worker: cache phân tích nằm trong bộ nhớ tiến trình.
ENTRYPOINT ["api-entrypoint"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
