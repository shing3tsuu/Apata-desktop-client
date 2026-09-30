import logging

def pytest_configure(config):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        force=True,
    )
    logging.getLogger('src.exceptions.exceptions').setLevel(logging.CRITICAL)
