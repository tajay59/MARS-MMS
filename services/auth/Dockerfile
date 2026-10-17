FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

# Build context is the repository root (compose passes `context: ..`) so mms_common is available.
COPY libs/mms_common /srv/libs/mms_common
RUN pip install /srv/libs/mms_common

COPY services/auth/pyproject.toml /srv/services/auth/pyproject.toml
COPY services/auth/app /srv/services/auth/app
RUN pip install /srv/services/auth

RUN useradd --system --uid 10001 mms
USER mms
WORKDIR /srv/services/auth
EXPOSE 8000
# Services are reachable only through Nginx on the internal network, so trust its
# X-Forwarded-* headers (the client IP goes into audit records).
ENV FORWARDED_ALLOW_IPS="*"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
