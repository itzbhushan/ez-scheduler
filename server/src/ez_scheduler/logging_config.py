"""Common logging configuration for EZ Scheduler application"""

import logging
import sys

from ez_scheduler.config import config


class InfoFilter(logging.Filter):
    """Filter to only allow INFO and DEBUG logs (exclude WARNING and above)"""

    def filter(self, record):
        return record.levelno < logging.WARNING


def setup_logging():
    """
    Configure logging to send INFO/DEBUG to stdout and WARNING/ERROR to stderr.
    Reads log level from application config.
    """
    # Get log level from config
    log_level = config.get("log_level", "INFO")
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")

    # Handler for INFO and DEBUG -> stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(InfoFilter())
    stdout_handler.setFormatter(formatter)

    # Handler for WARNING and ERROR -> stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add our custom handlers
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given module name.

    Args:
        name: Usually __name__ from the calling module

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
