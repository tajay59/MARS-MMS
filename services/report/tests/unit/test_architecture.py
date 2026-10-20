"""Rule-enforcement tests every service inherits from the template (TP "Rule-enforcement tests").

Do not weaken these. A failing check means the code broke a rule in CLAUDE.md.
"""

import subprocess
import sys
from pathlib import Path

from mms_common.checks import find_direct_produce

ROOT = Path(__file__).resolve().parents[2]


def test_domain_imports_follow_rule_7_and_layers_point_down():
    """Rule 7: app.domain has no FastAPI, Mongo or Kafka imports."""
    # A subprocess so import-linter's own import of the app can't leak into this test run.
    code = (
        "import sys; from importlinter.cli import lint_imports; "
        "sys.exit(lint_imports(config_filename='pyproject.toml', no_cache=True, no_logo=True))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Contracts: 2 kept, 0 broken" in result.stdout, result.stdout


def test_no_direct_produce_rule_2():
    """Rule 2: nothing in app/ talks to Kafka producers. Events go through the outbox."""
    violations = find_direct_produce(ROOT / "app")
    assert not violations, "\n".join(str(v) for v in violations)
