"""The readiness check (W23-3): `infra/scripts/readiness.sh` says PASS for a site that is set up
as the TRD says and names what is wrong with one that is not.

No stack is needed. The outside checks run against a small HTTPS server here that answers as
Nginx should, changed one thing at a time; the host checks run against a made-up stack folder
with a `docker` that answers from files. Needs bash, curl and openssl."""

from __future__ import annotations

import http.server
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "readiness.sh"
BASH = shutil.which("bash")
OPENSSL = shutil.which("openssl")

pytestmark = pytest.mark.skipif(
    not (BASH and OPENSSL and shutil.which("curl")), reason="needs bash, curl and openssl"
)

APP = "app.test"
FILES = "files.test"
CSP = (
    f"default-src 'self'; img-src 'self' https://{FILES} data: blob:; "
    f"media-src 'self' https://{FILES} blob:; connect-src 'self' https://{FILES} wss://{APP}; "
    "script-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)
INDEX = '<html><script type="module" src="/assets/app-abc123.js"></script><div id="app"></div></html>'
MANIFEST = '{"name": "x", "display": "standalone", "icons": [{"src": "pwa-192x192.png"}, {"src": "pwa-512x512.png"}]}'
PROBLEM = "application/problem+json"
YEAR = "public, max-age=31536000, immutable"


@dataclass
class Answer:
    status: int = 200
    content_type: str = "text/html"
    cache: str | None = None
    body: str = ""


def good_routes() -> dict[str, Answer]:
    return {
        "/sw.js": Answer(content_type="application/javascript", cache="no-cache"),
        "/theme-init.js": Answer(content_type="application/javascript", cache="no-cache"),
        "/manifest.webmanifest": Answer(content_type="application/manifest+json", cache="no-cache", body=MANIFEST),
        "/index.html": Answer(cache="no-cache", body=INDEX),
        "/pwa-192x192.png": Answer(content_type="image/png"),
        "/pwa-512x512.png": Answer(content_type="image/png"),
        "/assets/app-abc123.js": Answer(content_type="application/javascript", cache=YEAR, body="const v=`1.2.3`"),
        "/internal/users": Answer(404),
        "/metrics": Answer(404),
        "/.well-known/x": Answer(404),
        "/.releases/x": Answer(404),
        "/api/v1/integrations/x": Answer(501, PROBLEM),
        "/api/v1/auth/branding": Answer(content_type="application/json", body="{}"),
        "/api/v1/users": Answer(401, PROBLEM),
        "/api/v1/stations": Answer(401, PROBLEM),
        "/api/v1/media/x": Answer(401, PROBLEM),
        "/api/v1/dashboard": Answer(401, PROBLEM),
        "/api/v1/notifications": Answer(401, PROBLEM),
        "/api/v1/nope": Answer(404, PROBLEM),
    }


@dataclass
class Site:
    """What the server answers. A test changes one thing; `reset` puts it back."""

    port: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    routes: dict[str, Answer] = field(default_factory=dict)
    files_root: Answer = field(default_factory=Answer)

    def reset(self) -> None:
        self.headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Strict-Transport-Security": "max-age=31536000",
            "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": CSP,
        }
        self.routes = good_routes()
        self.files_root = Answer(403, "application/xml")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    folder = tmp_path_factory.mktemp("readiness-tls")
    made = subprocess.run(
        [OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", f"/CN={APP}",
         "-keyout", str(folder / "key.pem"), "-out", str(folder / "cert.pem")],
        capture_output=True, text=True, check=False,
        # Git Bash would turn /CN=... into a Windows path
        env={**os.environ, "MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*"},
    )
    assert made.returncode == 0, made.stderr
    site = Site()
    site.reset()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.headers.get("Host", "").startswith(FILES):
                answer = site.files_root
                headers = {k: v for k, v in site.headers.items()
                           if k in ("X-Content-Type-Options", "Strict-Transport-Security")}
            else:
                # Anything else is the app: Nginx's fallback to index.html
                answer = site.routes.get(self.path, Answer(cache="no-cache", body=INDEX))
                headers = site.headers
            body = answer.body.encode()
            self.send_response(answer.status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Type", answer.content_type)
            if answer.cache:
                self.send_header("Cache-Control", answer.cache)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(folder / "cert.pem", folder / "key.pem")
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    site.port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield site
    httpd.shutdown()


@pytest.fixture
def site(server):
    server.reset()
    return server


def outside(site: Site, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, str(SCRIPT), f"https://{APP}", "--files", FILES, "--insecure",
         "--via", f"127.0.0.1:{site.port}", *extra],
        capture_output=True, text=True, check=False,
    )


def failures(done: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in done.stdout.splitlines() if line.startswith("FAIL")]


def test_a_site_set_up_as_the_trd_says_passes(site):
    done = outside(site, "--expect-version", "1.2.3")
    assert done.returncode == 0, done.stdout + done.stderr
    assert failures(done) == []
    assert "PASS  the app is version 1.2.3" in done.stdout
    assert "PASS  the content security policy is the TRD's" in done.stdout
    # A self-signed certificate and one port: these two cannot be checked here, and it says so
    assert "SKIP  certificates" in done.stdout and "SKIP  http goes to https" in done.stdout


def test_the_files_host_is_read_from_the_policy_when_not_given(site):
    done = subprocess.run(
        [BASH, str(SCRIPT), f"https://{APP}", "--insecure", "--via", f"127.0.0.1:{site.port}"],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stdout
    assert f"INFO  files host: {FILES}" in done.stdout


def weaker_policy(site: Site) -> None:
    site.headers["Content-Security-Policy"] = CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")


def cached_worker(site: Site) -> None:
    site.routes["/sw.js"].cache = "max-age=3600"


def open_internal(site: Site) -> None:
    site.routes["/internal/users"] = Answer(200)


def operations_down(site: Site) -> None:
    site.routes["/api/v1/stations"] = Answer(503, PROBLEM)


def framed(site: Site) -> None:
    del site.headers["X-Frame-Options"]


def listing(site: Site) -> None:
    site.files_root = Answer(200, "application/xml")


def lost_icon(site: Site) -> None:
    site.routes["/pwa-512x512.png"] = Answer(404)


def browser_tab(site: Site) -> None:
    site.routes["/manifest.webmanifest"].body = MANIFEST.replace("standalone", "browser")


def short_lived_assets(site: Site) -> None:
    site.routes["/assets/app-abc123.js"].cache = "no-cache"


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (weaker_policy, "the content security policy is the TRD's"),
        (cached_worker, "/sw.js is served and never cached"),
        (open_internal, "/internal/ is not routed"),
        (operations_down, "operations answers"),
        (framed, "security headers on"),
        (listing, "the files host lists nothing to a stranger"),
        (lost_icon, "the manifest's icons load"),
        (browser_tab, "the manifest opens the app standalone"),
        (short_lived_assets, "hashed files are kept for a year"),
    ],
)
def test_one_thing_wrong_is_named_and_nothing_else(site, change, said):
    change(site)
    done = outside(site)
    assert done.returncode == 1
    found = failures(done)
    assert found and all(said in line for line in found), done.stdout


def test_another_version_than_expected_fails(site):
    done = outside(site, "--expect-version", "9.9.9")
    assert done.returncode == 1
    assert failures(done) == ["FAIL  the app is version 9.9.9: no script the page loads carries it"]


def test_a_site_that_does_not_answer_says_so_once_and_stops(site):
    done = subprocess.run(
        [BASH, str(SCRIPT), f"https://{APP}", "--files", FILES, "--insecure", "--via", "127.0.0.1:9"],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 1
    assert failures(done) == ["FAIL  the app answers: / answered 000"]
    assert done.stdout.splitlines()[-1] == "1 passed, 1 failed, 0 skipped"


def test_http_is_refused_as_an_address(site):
    done = subprocess.run([BASH, str(SCRIPT), "http://127.0.0.1:9", "--files", FILES, "--insecure"],
                          capture_output=True, text=True, check=False)
    assert "FAIL  the address is https" in done.stdout


# --- On the host ---------------------------------------------------------------------------

EXAMPLE = """\
# dev-only values
MMS_HOST=mms.localhost
FILES_HOST=files.mms.localhost
REDIS_PASSWORD=dev-redis-password
AUTH_TOTP_KEY=ZGV2LW9ubHkta2V5
MEDIA_SCAN_MODE=off
MONGO_DEV_PORT=27018
AUTH_SEED_PASSWORD=
PLATFORM_SMTP_HOST=mailpit
MMS_ALERT_EMAILS=
BACKUP_AGE_RECIPIENT=
"""
STAGING = {
    "MMS_ENVIRONMENT": "staging", "MMS_REGISTRY": "ghcr.io/x/y", "MMS_TLS_DIR": "/opt/mms/tls",
    "MMS_SECRETS_DIR": "/opt/mms/secrets", "MMS_HOST": "a.example.org", "FILES_HOST": "f.example.org",
    "REDIS_PASSWORD": "s3cr3t-value-one", "AUTH_TOTP_KEY": "s3cr3t-value-two", "MEDIA_SCAN_MODE": "off",
    "PLATFORM_SMTP_HOST": "smtp.gmail.com", "MMS_ALERT_EMAILS": "", "BACKUP_AGE_RECIPIENT": "",
}
PRODUCTION = STAGING | {
    "MMS_ENVIRONMENT": "production", "MEDIA_SCAN_MODE": "clamd", "COMPOSE_PROFILES": "backup",
    "PLATFORM_SMTP_HOST": "relay.example.org", "MMS_ALERT_EMAILS": "ops@example.org",
    "BACKUP_AGE_RECIPIENT": "age1qqqqqqqq",
}
HEALTHY = "nginx running healthy 0\nauth running healthy 0\nredis running  0\nkafka-init exited  0\n"
DOCKER = """\
#!/usr/bin/env bash
# A docker that answers from files in $FAKE
case "$*" in
  *" config -q") cat "$FAKE/config" >&2; exit "$(cat "$FAKE/config.code")" ;;
  *" ps -a "*) cat "$FAKE/ps" ;;
  *verify-audit*) cat "$FAKE/audit"; exit "$(cat "$FAKE/audit.code")" ;;
  *mms_backup_*) all="$*"; name="${all##*/textfile/}"; cat "$FAKE/$name" 2> /dev/null || exit 1 ;;
  *mongosh*) echo "8.0" ;;
  info*) echo "$FAKE" ;;
esac
"""


@dataclass
class Host:
    infra: Path
    fake: Path
    env: dict[str, str]

    def write(self, name: str, text: str) -> None:
        (self.fake / name).write_text(text, encoding="utf-8", newline="")

    def backup(self, kind: str, metric: str, hours_ago: float) -> None:
        self.write(f"mms_backup_{kind}.prom",
                   f"# HELP {metric} x\n# TYPE {metric} gauge\n{metric}{{kind=\"{kind}\"}} {int(time.time() - hours_ago * 3600)}\n")

    def run(self, values: dict[str, str], **env: str) -> subprocess.CompletedProcess[str]:
        target = self.infra / ".env"
        target.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8", newline="")
        target.chmod(0o600)
        return subprocess.run([BASH, str(SCRIPT), "--on-host", self.infra.as_posix()],
                              capture_output=True, text=True, check=False, env={**self.env, **env})


@pytest.fixture
def host(tmp_path):
    infra = tmp_path / "mms" / "infra"
    fake = tmp_path / "fake"
    bin_dir = tmp_path / "bin"
    for folder in (infra, fake, bin_dir):
        folder.mkdir(parents=True)
    (infra / ".env.example").write_text(EXAMPLE, encoding="utf-8", newline="")
    docker = bin_dir / "docker"
    docker.write_text(DOCKER, encoding="utf-8", newline="")
    docker.chmod(0o755)
    made = Host(infra, fake, {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE": fake.as_posix(),
        "READINESS_KERNEL": "5.15.0-100-generic",
    })
    made.write("config", "")
    made.write("config.code", "0")
    made.write("ps", HEALTHY)
    made.write("audit", "audit chain ok: 373 records\n")
    made.write("audit.code", "0")
    return made


def with_backups(host: Host, hours_ago: float = 3) -> None:
    host.write("ps", HEALTHY + "backup running  0\n")
    for kind in ("mongo", "config", "objects"):
        host.backup(kind, "backup_last_success_timestamp_seconds", hours_ago)
    host.backup("drill", "restore_drill_last_success_timestamp_seconds", 48)
    (host.infra.parent / ".deployed-tag").write_text("abc123\n", encoding="utf-8")


def test_a_staging_host_passes_and_says_what_it_did_not_check(host):
    done = host.run(STAGING)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PASS  the audit chain verifies (373 records)" in done.stdout
    assert "PASS  every container is healthy (4 in all)" in done.stdout
    assert "SKIP  backups" in done.stdout
    assert "INFO  MongoDB feature compatibility version: 8.0" in done.stdout


def test_a_production_host_passes(host):
    with_backups(host)
    done = host.run(PRODUCTION)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PASS  the last mongo backup is under 26 hours old" in done.stdout
    assert "PASS  the last restore drill is under 8 days old" in done.stdout
    assert "INFO  release: abc123" in done.stdout


def test_no_value_from_the_env_file_is_ever_printed(host):
    with_backups(host)
    for values in (STAGING, PRODUCTION, PRODUCTION | {"REDIS_PASSWORD": "dev-redis-password"}):
        done = host.run(values)
        for secret in ("s3cr3t-value-one", "s3cr3t-value-two", "dev-redis-password", "age1qqqqqqqq", "ops@example.org"):
            assert secret not in done.stdout + done.stderr


def test_a_secret_left_at_the_examples_value_is_named(host):
    done = host.run(STAGING | {"REDIS_PASSWORD": "dev-redis-password"})
    assert failures(done) == ["FAIL  no secret has the example's value: regenerate: REDIS_PASSWORD"]


def test_production_needs_every_key_staging_is_only_told(host):
    with_backups(host)
    values = {k: v for k, v in PRODUCTION.items() if k != "FILES_HOST"}
    assert failures(host.run(values)) == ["FAIL  every key of .env.example is in .env: missing: FILES_HOST"]
    staging = host.run({k: v for k, v in STAGING.items() if k != "FILES_HOST"})
    assert staging.returncode == 0
    assert "INFO  keys of .env.example not set here: FILES_HOST" in staging.stdout


def test_a_variable_compose_needs_is_reported_in_its_words(host):
    host.write("config", "required variable AUTH_TOTP_KEY is missing a value\n")
    host.write("config.code", "1")
    done = host.run(STAGING)
    assert failures(done) == ["FAIL  the stack's files accept this .env: required variable AUTH_TOTP_KEY is missing a value"]


def test_production_refuses_staging_habits(host):
    with_backups(host)
    done = host.run(PRODUCTION | {
        "MEDIA_SCAN_MODE": "off", "PLATFORM_SMTP_HOST": "smtp.gmail.com", "MMS_ALERT_EMAILS": "",
        "BACKUP_AGE_RECIPIENT": "", "COMPOSE_PROFILES": "", "AUTH_SEED_PASSWORD": "x",
    })
    said = "\n".join(failures(done))
    for words in ("the seed users' password is not set", "files are scanned", "the backup profile is on",
                  "backups are encrypted to a public key", "alerts have a recipient", "organization's relay (T3)"):
        assert words in said


def test_production_without_backups_fails(host):
    done = host.run(PRODUCTION)
    said = "\n".join(failures(done))
    assert "backups run: the backup container is not running" in said
    assert "the release that runs is recorded" in said


def test_an_old_backup_and_an_old_drill_fail(host):
    with_backups(host, hours_ago=30)
    host.backup("drill", "restore_drill_last_success_timestamp_seconds", 24 * 9)
    found = failures(host.run(PRODUCTION))
    assert "FAIL  the last mongo backup is under 26 hours old: 30 hours" in found
    assert "FAIL  the last restore drill is under 8 days old: 9 days" in found


def test_a_drill_run_elsewhere_is_not_a_failure_here(host):
    with_backups(host)
    (host.fake / "mms_backup_drill.prom").unlink()
    done = host.run(PRODUCTION)
    assert done.returncode == 0, done.stdout
    assert "INFO  no restore drill is recorded on this host" in done.stdout


def test_an_unhealthy_container_is_named(host):
    host.write("ps", HEALTHY + "media running unhealthy 0\nreport exited  1\n")
    assert failures(host.run(STAGING)) == ["FAIL  every container is healthy (6 in all): look at: media report"]


def test_a_broken_audit_chain_fails(host):
    host.write("audit", "audit chain BROKEN at seq 12\n")
    host.write("audit.code", "1")
    assert failures(host.run(STAGING)) == ["FAIL  the audit chain verifies: audit chain BROKEN at seq 12"]


@pytest.mark.parametrize(("kernel", "safe"), [
    ("5.15.0-100-generic", True), ("6.8.0-45-generic", True), ("6.19.3", False),
    ("7.0.13-generic", False), ("7.0.14", True), ("7.1.0", True),
])
def test_the_kernels_mongod_cannot_start_on(host, kernel, safe):
    done = host.run(STAGING, READINESS_KERNEL=kernel)
    assert ("PASS  the kernel is safe for mongod" in done.stdout) is safe


@pytest.mark.skipif(sys.platform == "win32", reason="file modes are a Linux check")
def test_an_env_file_others_can_read_fails(host):
    host.run(STAGING)
    (host.infra / ".env").chmod(0o644)
    done = subprocess.run([BASH, str(SCRIPT), "--on-host", host.infra.as_posix()],
                          capture_output=True, text=True, check=False, env=host.env)
    assert "FAIL  .env is readable by its owner only: mode 644, expected 600" in done.stdout
