from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Iterable

PACKAGE_LOGGER_NAME = 'mcp_catalog'
_LOGGER = logging.getLogger(PACKAGE_LOGGER_NAME)


class _BufferingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


_BUFFER = _BufferingHandler()
_CONFIGURED = False


def _replace_handlers(handlers: Iterable[logging.Handler]) -> None:
    for handler in _LOGGER.handlers[:]:
        _LOGGER.removeHandler(handler)
        if handler is not _BUFFER:
            handler.close()
    for handler in handlers:
        _LOGGER.addHandler(handler)


def begin_buffering() -> None:
    """Buffer package logs until CLI settings are available."""
    global _CONFIGURED
    _BUFFER.records.clear()
    _replace_handlers([_BUFFER])
    _LOGGER.setLevel(logging.DEBUG)
    _LOGGER.propagate = False
    _CONFIGURED = False


def is_configured() -> bool:
    return _CONFIGURED


def _level_number(value: str) -> int:
    level = logging.getLevelName(value.upper())
    if not isinstance(level, int):
        raise ValueError(
            f'Unknown log level {value!r}; use DEBUG, INFO, WARNING, ERROR, or CRITICAL.'
        )
    if level == logging.NOTSET:
        raise ValueError('NOTSET is not a supported log level.')
    return level


def _parse_log_file(specification: str, default_level: int) -> tuple[int, Path]:
    prefix, separator, filepath = specification.partition(':')
    if separator and prefix.upper() in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}:
        level, path_value = _level_number(prefix), filepath
    else:
        level, path_value = default_level, specification
    if not path_value:
        raise ValueError(f'Log file path is empty in {specification!r}.')
    return level, Path(path_value).expanduser()


def configure_logging(log_level: str = 'INFO', log_files: Iterable[str] = ()) -> None:
    """Configure stderr and optional file handlers, then emit buffered records."""
    global _CONFIGURED
    default_level = _level_number(log_level)
    handlers: list[logging.Handler] = []
    try:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(default_level)
        handlers.append(stderr_handler)
        for specification in log_files:
            level, path = _parse_log_file(specification, default_level)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding='utf-8')
            file_handler.setLevel(level)
            handlers.append(file_handler)
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        for handler in handlers:
            handler.setFormatter(formatter)
    except Exception:
        for handler in handlers:
            handler.close()
        raise

    records = _BUFFER.records[:]
    _replace_handlers(handlers)
    _CONFIGURED = True
    for record in records:
        for handler in handlers:
            if record.levelno >= handler.level:
                handler.handle(record)
    _BUFFER.records.clear()


def dump_buffer_to_stderr() -> None:
    """Write all buffered package records to stderr if CLI setup failed."""
    if not _BUFFER.records:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(
        logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
    )
    for record in _BUFFER.records:
        handler.handle(record)
    handler.flush()
    handler.close()
    _BUFFER.records.clear()


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the package namespace."""
    if name == PACKAGE_LOGGER_NAME or name.startswith(f'{PACKAGE_LOGGER_NAME}.'):
        return logging.getLogger(name)
    return logging.getLogger(f'{PACKAGE_LOGGER_NAME}.{name}')


begin_buffering()
