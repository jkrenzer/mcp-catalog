#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import IO

logger = logging.getLogger('agentic-memory-entrypoint')
ENVIRONMENT_VARIABLES = (
    'CONFIG_DIR',
    'MEMORY_DIR',
    'AMEM_BRAIN',
    'MCP_SERVER_PORT',
    'MCP_SERVER_HOST',
    'MCP_SERVER_PROTOCOL',
    'MCP_SERVER_LOG_LEVEL',
    'MCP_SERVER_LOG_FILE',
    'MCP_SERVER_TOKEN_FILE',
    'AGENTIC_TOKEN',
    'RUST_LOG',
    'IMPORT_MEMORY_FILE',
    'EXPORT_MEMORY_FILE',
    'EXPORT_MEMORY_INTERVAL',
)


def _env(name: str, default: str = '') -> str:
    """Return an environment variable, treating empty values as unset."""
    return os.environ.get(name) or default


def _log_environment() -> None:
    defaults = {
        'CONFIG_DIR': '/config',
        'MEMORY_DIR': '/memory',
        'MCP_SERVER_PORT': '3000',
        'MCP_SERVER_HOST': '0.0.0.0',
        'MCP_SERVER_PROTOCOL': 'stdio',
        'MCP_SERVER_LOG_LEVEL': 'info',
        'MCP_SERVER_LOG_FILE': '',
        'MCP_SERVER_TOKEN_FILE': '',
        'AGENTIC_TOKEN': '',
        'RUST_LOG': 'info',
        'IMPORT_MEMORY_FILE': '',
        'EXPORT_MEMORY_FILE': '',
        'EXPORT_MEMORY_INTERVAL': '60',
    }
    logger.info('Container startup environment:')
    for name in ENVIRONMENT_VARIABLES:
        value = _env(name, defaults.get(name, '<unset>'))
        if name == 'AGENTIC_TOKEN':
            value = '<redacted>' if value else '<not set>'
        logger.info('  %s=%s', name, value)


def _load_token_file() -> None:
    token_file_value = _env('MCP_SERVER_TOKEN_FILE')
    if not token_file_value:
        return

    token_file = Path(token_file_value).expanduser()
    if not token_file.exists():
        logger.info('MCP_SERVER_TOKEN_FILE does not exist: %s', token_file)
        return
    if not token_file.is_file():
        raise ValueError(
            f'MCP_SERVER_TOKEN_FILE is not a file: {token_file} '
            '(mount the token as a file, not a directory)'
        )

    token = token_file.read_text(encoding='utf-8').strip()
    if not token:
        raise ValueError(f'MCP_SERVER_TOKEN_FILE is empty: {token_file}')
    os.environ['AGENTIC_TOKEN'] = token
    logger.info('Loaded AGENTIC_TOKEN from %s', token_file)


def _required_choice(name: str, value: str, choices: set[str]) -> str:
    if value not in choices:
        raise ValueError(f'{name} must be one of: {", ".join(sorted(choices))}')
    return value


def _python_log_level(value: str) -> int:
    normalized = value.strip().lower()
    levels = {
        'trace': logging.DEBUG,
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL,
    }
    try:
        return levels[normalized]
    except KeyError as error:
        raise ValueError(
            'MCP_SERVER_LOG_LEVEL must be one of: trace, debug, info, warn, error, critical'
        ) from error


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def _run_checked(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, check=True, stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        rendered_command = ' '.join(command)
        raise RuntimeError(
            f'command failed with exit status {error.returncode}: {rendered_command}'
        ) from error


def _write_config(
    config_dir: Path,
    memory_path: Path,
    protocol: str,
    address: str,
    log_level: str,
) -> Path:
    config_path = config_dir / 'agentic-memory.toml'
    config = (
        f'memory_path = {json.dumps(str(memory_path))}\n'
        f'transport = {json.dumps("sse" if protocol == "http" else "stdio")}\n'
        f'sse_addr = {json.dumps(address)}\n'
        'auto_save_interval = 30\n'
        f'log_level = {json.dumps(log_level)}\n'
    )
    _atomic_write(config_path, config.encode('utf-8'))
    return config_path


def _init_memory(memory_path: Path) -> None:
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    if not memory_path.exists():
        _run_checked(['amem', 'init', str(memory_path)])


def _import_memory(import_path: Path, memory_path: Path) -> None:
    """Import a snapshot, or start with an empty memory when there is nothing to import."""
    suffix = import_path.suffix.lower()
    if suffix not in {'.amem', '.json'}:
        raise ValueError('IMPORT_MEMORY_FILE must end in .amem or .json')
    if not import_path.is_file():
        logger.warning('No import memory found at %s; starting with an empty memory', import_path)
        _init_memory(memory_path)
        return
    if import_path.stat().st_size == 0:
        logger.warning('Import memory file %s is empty; starting with an empty memory', import_path)
        _init_memory(memory_path)
        return

    logger.info('Importing memory from %s into %s', import_path, memory_path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == '.amem':
        if import_path.resolve() != memory_path.resolve():
            fd, temporary_path = tempfile.mkstemp(
                prefix=f'.{memory_path.name}.', dir=memory_path.parent
            )
            os.close(fd)
            try:
                shutil.copyfile(import_path, temporary_path)
                os.replace(temporary_path, memory_path)
            except BaseException:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
                raise
    else:
        if not memory_path.exists():
            _run_checked(['amem', 'init', str(memory_path)])
        _run_checked(['amem', 'import', str(memory_path), str(import_path)])

    if memory_path.exists():
        memory_path.chmod(0o600)
    logger.info('Memory import completed')


def _export_memory(export_path: Path, memory_path: Path) -> None:
    logger.info('Exporting memory from %s to %s', memory_path, export_path)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    if export_path.resolve() == memory_path.resolve():
        raise ValueError('EXPORT_MEMORY_FILE must not be the working AMEM_BRAIN file')
    suffix = export_path.suffix.lower()
    if suffix not in {'.amem', '.json'}:
        raise ValueError('EXPORT_MEMORY_FILE must end in .amem or .json')

    exported_json = _run_checked(['amem', 'export', str(memory_path), '--pretty']).stdout
    if suffix == '.json':
        _atomic_write(export_path, exported_json)
        logger.info('Memory export completed: %s', export_path)
        return

    with tempfile.TemporaryDirectory(prefix='.amem-export-', dir=export_path.parent) as tmp:
        temporary_dir = Path(tmp)
        json_path = temporary_dir / 'memory.json'
        snapshot_path = temporary_dir / 'memory.amem'
        json_path.write_bytes(exported_json)
        _run_checked(['amem', 'init', str(snapshot_path)])
        _run_checked(['amem', 'import', str(snapshot_path), str(json_path)])
        os.replace(snapshot_path, export_path)
    logger.info('Memory export completed: %s', export_path)


def _open_log_file(value: str) -> Path | None:
    """Prepare MCP_SERVER_LOG_FILE and mirror the wrapper's own log records into it."""
    if not value:
        return None
    log_file = Path(value).expanduser()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding='utf-8')
    except OSError as error:
        logger.warning(
            'Cannot write MCP_SERVER_LOG_FILE %s (%s); logging to stderr only', log_file, error
        )
        return None
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logging.getLogger().addHandler(handler)
    logger.info('Duplicating log output to %s', log_file)
    return log_file


def _forward_stderr(source: IO[bytes], log_file: Path | None) -> None:
    """Copy the server's stderr to our stderr and, when configured, to the log file."""
    sink = None
    if log_file is not None:
        try:
            sink = log_file.open('ab')
        except OSError as error:
            logger.warning('Cannot append server output to %s: %s', log_file, error)
    try:
        for line in iter(source.readline, b''):
            sys.stderr.buffer.write(line)
            sys.stderr.buffer.flush()
            if sink is not None:
                sink.write(line)
                sink.flush()
    finally:
        if sink is not None:
            sink.close()


def _address(host: str, port: str) -> str:
    try:
        parsed_port = int(port)
    except ValueError as error:
        raise ValueError('MCP_SERVER_PORT must be an integer from 1 to 65535') from error
    if not 1 <= parsed_port <= 65535:
        raise ValueError('MCP_SERVER_PORT must be an integer from 1 to 65535')
    if not host:
        raise ValueError('MCP_SERVER_HOST must not be empty')
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'
    return f'{host}:{parsed_port}'


def _server_command(
    protocol: str, memory_path: Path, config_path: Path, address: str, log_level: str
) -> list[str]:
    command = ['agentic-memory-mcp', 'serve' if protocol == 'stdio' else 'serve-http']
    if protocol == 'http':
        command.extend(['--addr', address])
    command.extend(
        [
            '--memory',
            str(memory_path),
            '--config',
            str(config_path),
            '--log-level',
            log_level,
        ]
    )
    return command


def main() -> int:
    wrapper_log_level = _python_log_level(_env('MCP_SERVER_LOG_LEVEL', 'info'))
    logging.basicConfig(
        level=wrapper_log_level,
        format='%(asctime)s %(levelname)s %(message)s',
        stream=sys.stderr,
        force=True,
    )
    log_file = _open_log_file(_env('MCP_SERVER_LOG_FILE'))
    _load_token_file()
    _log_environment()
    config_dir = Path(_env('CONFIG_DIR', '/config')).expanduser().resolve()
    memory_dir = Path(_env('MEMORY_DIR', '/memory')).expanduser().resolve()
    memory_path = Path(_env('AMEM_BRAIN', str(memory_dir / '.brain.amem'))).expanduser().resolve()
    protocol = _required_choice(
        'MCP_SERVER_PROTOCOL', _env('MCP_SERVER_PROTOCOL', 'stdio'), {'stdio', 'http'}
    )
    log_level = _required_choice(
        'RUST_LOG',
        _env('RUST_LOG', 'info').lower(),
        {'error', 'warn', 'info', 'debug', 'trace'},
    )
    address = _address(
        _env('MCP_SERVER_HOST', '0.0.0.0'),
        _env('MCP_SERVER_PORT', '3000'),
    )
    if protocol == 'http' and not _env('AGENTIC_TOKEN'):
        raise ValueError('AGENTIC_TOKEN is required when MCP_SERVER_PROTOCOL=http')

    config_path = _write_config(config_dir, memory_path, protocol, address, log_level)
    logger.info('Wrote server configuration to %s', config_path)
    import_path = _env('IMPORT_MEMORY_FILE')
    if import_path:
        _import_memory(Path(import_path).expanduser().resolve(), memory_path)
    else:
        _init_memory(memory_path)

    export_value = _env('EXPORT_MEMORY_FILE')
    export_path = Path(export_value).expanduser().resolve() if export_value else None
    try:
        export_interval = int(_env('EXPORT_MEMORY_INTERVAL', '60'))
    except ValueError as error:
        raise ValueError('EXPORT_MEMORY_INTERVAL must be a positive integer') from error
    if export_interval <= 0:
        raise ValueError('EXPORT_MEMORY_INTERVAL must be a positive integer')
    if export_path is not None:
        if export_path.resolve() == memory_path.resolve():
            raise ValueError('EXPORT_MEMORY_FILE must not be the working AMEM_BRAIN file')
        if export_path.suffix.lower() not in {'.amem', '.json'}:
            raise ValueError('EXPORT_MEMORY_FILE must end in .amem or .json')

    child: subprocess.Popen[bytes] | None = None
    shutdown_signal: int | None = None

    def forward_signal(signum: int, _frame: object) -> None:
        nonlocal shutdown_signal
        shutdown_signal = signum
        if child is not None and child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)
    command = _server_command(protocol, memory_path, config_path, address, log_level)
    logger.info('Starting MCP server: %s', ' '.join(command))
    child = subprocess.Popen(command, stderr=subprocess.PIPE)
    assert child.stderr is not None
    forwarder = threading.Thread(target=_forward_stderr, args=(child.stderr, log_file), daemon=True)
    forwarder.start()
    logger.info('MCP server started (pid=%s)', child.pid)
    next_export = time.monotonic() + export_interval

    try:
        while True:
            if export_path is None:
                return_code = child.wait()
                break
            timeout = max(0.0, next_export - time.monotonic())
            try:
                return_code = child.wait(timeout=timeout)
                break
            except subprocess.TimeoutExpired:
                if child.poll() is not None:
                    return_code = child.returncode
                    break
                try:
                    _export_memory(export_path, memory_path)
                except (OSError, RuntimeError, ValueError):
                    logger.exception('Periodic memory export failed')
                next_export = time.monotonic() + export_interval
    finally:
        forwarder.join(timeout=5)
        logger.info(
            'MCP server stopped (pid=%s, exit_code=%s%s)',
            child.pid,
            child.returncode,
            f', signal={shutdown_signal}' if shutdown_signal is not None else '',
        )
        if export_path is not None:
            try:
                _export_memory(export_path, memory_path)
            except (OSError, RuntimeError, ValueError):
                logger.exception('Final memory export failed')
                if child.returncode == 0:
                    return_code = 1

    if shutdown_signal is not None and return_code == 0:
        return 128 + shutdown_signal
    return return_code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        logger.error('entrypoint error: %s', error)
        raise SystemExit(1) from error
