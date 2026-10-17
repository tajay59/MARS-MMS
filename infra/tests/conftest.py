def pytest_configure(config):
    config.addinivalue_line(
        "markers", "req(id): requirement ID from the PRD that the test covers (docs/TP.md)"
    )
