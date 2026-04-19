#!/usr/bin/env python
"""Logging customization"""

import logging
import sys


def handle_exception(exc_type, exc_value, exc_traceback):
    # Ignore KeyboardInterrupt to allow graceful exit
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
    )


def log_output(self, message, *args, **kws):
    if self.isEnabledFor(logging.OUTPUT):
        self._log(logging.OUTPUT, message, args, **kws)


def log_input(self, message, *args, **kws):
    if self.isEnabledFor(logging.INPUT):
        self._log(logging.INPUT, message, args, **kws)


def get_output(message, *args, **kwargs):
    logging.getLogger().output(message, *args, **kwargs)


def get_input(message, *args, **kwargs):
    logging.getLogger().input(message, *args, **kwargs)


class CustomFormatter(logging.Formatter):
    LEVELS = {
        logging.DEBUG: "[-]",
        logging.INFO: "[.]",
        logging.WARNING: "[*]",
        logging.ERROR: "[?]",
        logging.CRITICAL: "[!]",
    }

    def format(self, record):
        original = record.levelname
        record.levelname = self.LEVELS.get(record.levelno, original)
        return super().format(record)


# Create custom levels
logging.OUTPUT = logging.DEBUG + 1
logging.INPUT = logging.DEBUG + 2
logging.addLevelName(logging.INPUT, "-->")
logging.addLevelName(logging.OUTPUT, "<--")

logging.Logger.output = log_output
logging.Logger.input = log_input
logging.output = get_output
logging.input = get_input

# Set exception hook
sys.excepthook = handle_exception

if __name__ == "__main__":
    # Create a test logger
    logger = logging.getLogger("")
    logger.setLevel(logging.OUTPUT)

    # Create a console handler with the custom formatter
    handler = logging.StreamHandler()
    handler.setFormatter(
        CustomFormatter("%(levelname)s %(asctime)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)

    # Print messages at standard levels
    logging.debug("Debug message")
    logging.info("Info message")
    logging.warning("Warning message")
    logging.error("Error message")
    logging.critical("Critical message")

    # Print messages at custom levels
    logging.output("Output message")
    logging.input("Input message")

    # Log an exception with traceback
    n = 1 / 0
