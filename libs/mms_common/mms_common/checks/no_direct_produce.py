"""Rule 2: request handlers never produce to Kafka. Only `mms_common` talks to a producer.

A service's `app/` package may not import `aiokafka` at all. Events are written to the
outbox in the record's transaction; the relay in `mms_common.outbox` publishes them, and
consumers run through `mms_common.kafka`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_MODULES = ("aiokafka", "kafka", "confluent_kafka")
FORBIDDEN_NAMES = ("AIOKafkaProducer", "send_and_wait")


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    what: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.what}"


def _is_forbidden_module(name: str) -> bool:
    return any(name == m or name.startswith(m + ".") for m in FORBIDDEN_MODULES)


def find_direct_produce(root: Path) -> list[Violation]:
    found: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found += [
                    Violation(path, node.lineno, f"imports {a.name}")
                    for a in node.names
                    if _is_forbidden_module(a.name)
                ]
            elif isinstance(node, ast.ImportFrom):
                if node.module and _is_forbidden_module(node.module):
                    found.append(Violation(path, node.lineno, f"imports from {node.module}"))
            elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
                found.append(Violation(path, node.lineno, f"uses .{node.attr}"))
            elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                found.append(Violation(path, node.lineno, f"uses {node.id}"))
    return found
