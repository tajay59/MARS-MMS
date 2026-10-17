# The `web` image for staging and production: Nginx with its config and the SPA build baked
# in (TRD §2.1, §18). Locally, compose.yml mounts the config and frontend/dist instead.
# Build context: the repository root.
#
# CI first builds frontend/dist and runs infra/scripts/carry_assets.py, which writes this
# release's manifest into dist/.releases/ and copies the assets of releases replaced in the
# last 7 days into infra/nginx/carry/ (PWA finding F9). dist is copied over carry.

FROM nginx:1.31.7-alpine
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/snippets /etc/nginx/snippets
COPY infra/nginx/templates /etc/nginx/templates
COPY infra/nginx/carry/ /usr/share/nginx/html/
COPY frontend/dist/ /usr/share/nginx/html/
