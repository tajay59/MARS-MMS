# The visual regression check of the visit report (W16 slice 3): the report's PDFs are drawn in the
# same system as production (Pango, Inter and JetBrains Mono from the report image) and compared
# with the committed pictures in visual/baselines. Build context: the repository root.
#
#   docker build -f services/report/visual/Dockerfile -t mms-report-visual .
#   docker run --rm -v "$PWD/visual-out:/out" mms-report-visual              # compare
#   docker run --rm -v "$PWD/services/report/visual/baselines:/srv/services/report/visual/baselines" \
#       mms-report-visual python -m pytest visual --update-baselines          # accept a change
# pypdfium2 is pinned: the rasteriser's version changes anti-aliasing, and 5.15.0 moved 0.7% of the pixels
# of three baselines (2026-11-06). Update it together with the baselines (--update-baselines).
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MMS_VISUAL=1 MMS_VISUAL_OUT=/out
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        fonts-inter fonts-jetbrains-mono fontconfig \
    && rm -rf /var/lib/apt/lists/*
COPY libs/mms_common /srv/libs/mms_common
COPY services/report/pyproject.toml /srv/services/report/pyproject.toml
COPY services/report/app /srv/services/report/app
RUN pip install /srv/libs/mms_common /srv/services/report pytest pypdfium2==5.14.0 pillow
WORKDIR /srv/services/report
# Only the made-up visit the tests share, not the service's own tests (they need containers)
COPY services/report/tests/__init__.py services/report/tests/visit_facts.py /srv/services/report/tests/
COPY services/report/visual /srv/services/report/visual
CMD ["python", "-m", "pytest", "visual", "-q"]
