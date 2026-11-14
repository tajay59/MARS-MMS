"""`--update-baselines` accepts what the template draws now as the new baseline."""

from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption("--update-baselines", action="store_true", default=False,
                     help="write the baseline pictures instead of comparing with them")
