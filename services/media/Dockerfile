FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

# Build context is the repository root (compose passes `context: ..`) so mms_common is available.
COPY libs/mms_common /srv/libs/mms_common
RUN pip install /srv/libs/mms_common

COPY services/media/pyproject.toml /srv/services/media/pyproject.toml
COPY services/media/app /srv/services/media/app
RUN pip install /srv/services/media

# pip is not needed at run time, and it carries its own vendored copies of urllib3, msgpack
# and setuptools, which the image scan reports (TRD §15).
RUN pip uninstall --yes pip && rm -rf /usr/local/lib/python3.13/ensurepip

RUN useradd --system --uid 10001 mms
USER mms
WORKDIR /srv/services/media
EXPOSE 8000
# Services are reachable only through Nginx on the internal network, so trust its
# X-Forwarded-* headers (the client IP goes into audit records).
ENV FORWARDED_ALLOW_IPS="*"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
