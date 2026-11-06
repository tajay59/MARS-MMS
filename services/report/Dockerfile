FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

# WeasyPrint draws PDFs with Pango; Inter and JetBrains Mono are the brand fonts (DBD), so
# labels and reports print the same as the app. Chromium (the Debian package, so security fixes
# arrive with the image scan) draws the charts of the summary reports (W19-11): one process at a
# time, started by the worker on a page it writes itself, never reachable from the network.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        fonts-inter fonts-jetbrains-mono fontconfig chromium \
    && rm -rf /var/lib/apt/lists/*

# Build context is the repository root (compose passes `context: ..`) so mms_common is available.
COPY libs/mms_common /srv/libs/mms_common
RUN pip install /srv/libs/mms_common

COPY services/report/pyproject.toml /srv/services/report/pyproject.toml
COPY services/report/app /srv/services/report/app
RUN pip install /srv/services/report

# pip is not needed at run time, and it carries its own vendored copies of urllib3, msgpack
# and setuptools, which the image scan reports (TRD §15).
RUN pip uninstall --yes pip && rm -rf /usr/local/lib/python3.13/ensurepip

RUN useradd --system --uid 10001 mms
USER mms
WORKDIR /srv/services/report
EXPOSE 8000
# Services are reachable only through Nginx on the internal network, so trust its
# X-Forwarded-* headers (the client IP goes into audit records).
ENV FORWARDED_ALLOW_IPS="*"
# Two workers answer /metrics from one folder of files (mms_common.metrics, W20-1). The folder
# is emptied at every start: a restarted container keeps /tmp, and files of dead workers would
# be counted again. The queue workers (python -m app.worker) are one process and need none.
CMD ["sh", "-c", "export PROMETHEUS_MULTIPROC_DIR=/tmp/mms-metrics; rm -rf \"$PROMETHEUS_MULTIPROC_DIR\"; mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\"; exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers"]
