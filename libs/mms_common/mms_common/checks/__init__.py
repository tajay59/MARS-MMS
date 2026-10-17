"""Architecture checks that services run in their own tests (TP "Rule-enforcement tests")."""

from mms_common.checks.no_direct_produce import Violation, find_direct_produce

__all__ = ["Violation", "find_direct_produce"]
