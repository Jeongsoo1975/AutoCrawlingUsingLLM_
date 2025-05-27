# utils/logger.py
import logging
from config import settings
import sys
import io


def setup_logger():
    # Remove all handlers associated with the root logger object.
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Simple configuration without custom streams to avoid encoding issues
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format=settings.LOG_FORMAT,
        force=True  # Force reconfiguration
    )
    # Silence some verbose loggers if necessary
    logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx is used by ollama and playwright
    logging.getLogger("playwright").setLevel(logging.WARNING)


if __name__ == '__main__':
    setup_logger()
    logger = logging.getLogger(__name__)
    logger.debug("This is a debug message.")
    logger.info("This is an info message.")
    logger.warning("This is a warning message.")
    logger.error("This is an error message.")
    logger.critical("This is a critical message.")