import pytest
import logging

@pytest.fixture(autouse=True)
def setup_logging():
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        force=True,
        style="%"
    )