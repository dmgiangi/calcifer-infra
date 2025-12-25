import logging
import sys
from pathlib import Path

# System logger configuration (non-UI)
LOG_FILE = Path("calcifer.log")

def setup_logger():
    """
    Configures the standard Python logger to write to a file.
    Does not print to console to avoid cluttering the Rich UI.
    """
    logger = logging.getLogger("calcifer")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicates if initialized multiple times
    if logger.hasHandlers():
        return logger

    # Detailed formatting for debugging
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s] - %(message)s'
    )

    # File Handler (writes to calcifer.log)
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger

# Singleton instance
sys_logger = setup_logger()