import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / 'servers/agentralabs-agentic-memory-mcp/entrypoint.py'


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding='utf-8')
    path.chmod(0o755)


def _run_entrypoint(
    tmp_path: Path,
    *,
    server_sleep: str = '0',
    server_exit_code: str = '0',
    **overrides: str,
):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    call_log = tmp_path / 'calls.log'
    _write_executable(
        bin_dir / 'amem',
        '#!/bin/sh\n'
        'printf "amem %s\\n" "$*" >> "$CALL_LOG"\n'
        'case "$1" in\n'
        '  init) : > "$2" ;;\n'
        '  import) printf imported >> "$2" ;;\n'
        '  export) printf \'{"snapshot": true}\\n\' ;;\n'
        'esac\n',
    )
    _write_executable(
        bin_dir / 'agentic-memory-mcp',
        '#!/bin/sh\n'
        'printf "server %s\\n" "$*" >> "$CALL_LOG"\n'
        'printf "token=%s\\n" "$AGENTIC_TOKEN" >> "$CALL_LOG"\n'
        'if [ -n "$SERVER_STDERR_LINE" ]; then echo "$SERVER_STDERR_LINE" >&2; fi\n'
        'sleep "$SERVER_SLEEP"\n'
        'exit "$SERVER_EXIT_CODE"\n',
    )

    memory_dir = tmp_path / 'memory'
    env = os.environ.copy()
    env.update(
        {
            'PATH': f'{bin_dir}:{env["PATH"]}',
            'CALL_LOG': str(call_log),
            'SERVER_SLEEP': server_sleep,
            'SERVER_EXIT_CODE': server_exit_code,
            'CONFIG_DIR': str(tmp_path / 'config'),
            'MEMORY_DIR': str(memory_dir),
            'AMEM_BRAIN': str(memory_dir / '.brain.amem'),
            'MCP_SERVER_PROTOCOL': 'stdio',
            'MCP_SERVER_HOST': '127.0.0.1',
            'MCP_SERVER_PORT': '8123',
            'MCP_SERVER_LOG_LEVEL': 'info',
            'RUST_LOG': 'debug',
            'EXPORT_MEMORY_INTERVAL': '1',
        }
    )
    env.update(overrides)
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result, call_log


def test_json_import_happens_before_server_and_creates_config(tmp_path):
    import_path = tmp_path / 'seed.json'
    import_path.write_text('{"nodes": []}\n', encoding='utf-8')

    result, call_log = _run_entrypoint(
        tmp_path,
        IMPORT_MEMORY_FILE=str(import_path),
    )

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding='utf-8').splitlines()
    assert calls[0].startswith('amem init ')
    assert calls[1] == f'amem import {tmp_path}/memory/.brain.amem {import_path}'
    assert calls[2].startswith('server serve ')
    config = (tmp_path / 'config/agentic-memory.toml').read_text(encoding='utf-8')
    assert 'transport = "stdio"' in config
    assert 'sse_addr = "127.0.0.1:8123"' in config
    assert f'memory_path = {json.dumps(str(tmp_path / "memory/.brain.amem"))}' in config


def test_periodic_export_writes_native_snapshot_without_touching_live_brain(tmp_path):
    export_path = tmp_path / 'backups/brain.amem'

    result, call_log = _run_entrypoint(
        tmp_path,
        server_sleep='1.3',
        EXPORT_MEMORY_FILE=str(export_path),
    )

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding='utf-8').splitlines()
    assert calls[0].startswith('amem init ')
    assert calls[1].startswith('server serve ')
    assert sum(line.startswith('amem export ') for line in calls) >= 2
    assert export_path.read_text(encoding='utf-8') == 'imported'
    assert (tmp_path / 'memory/.brain.amem').read_bytes() == b''


def test_http_protocol_uses_http_transport_and_bind_address(tmp_path):
    result, call_log = _run_entrypoint(
        tmp_path,
        MCP_SERVER_PROTOCOL='http',
        AGENTIC_TOKEN='test-token',
    )

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding='utf-8').splitlines()
    assert any(line.startswith('server serve-http --addr 127.0.0.1:8123 ') for line in calls)
    config = (tmp_path / 'config/agentic-memory.toml').read_text(encoding='utf-8')
    assert 'transport = "sse"' in config
    assert 'test-token' not in result.stderr


def test_final_export_runs_after_server_exits_with_error_and_logs_lifecycle(tmp_path):
    export_path = tmp_path / 'backups/brain.json'

    result, call_log = _run_entrypoint(
        tmp_path,
        server_exit_code='7',
        EXPORT_MEMORY_FILE=str(export_path),
        AGENTIC_TOKEN='secret-test-token',
    )

    assert result.returncode == 7
    assert export_path.read_text(encoding='utf-8') == '{"snapshot": true}\n'
    calls = call_log.read_text(encoding='utf-8').splitlines()
    assert calls[0].startswith('amem init ')
    assert calls[1].startswith('server serve ')
    assert any(line.startswith('amem export ') for line in calls)
    assert 'CONFIG_DIR=' in result.stderr
    assert 'MCP_SERVER_LOG_LEVEL=info' in result.stderr
    assert f'EXPORT_MEMORY_FILE={export_path}' in result.stderr
    assert 'MCP server started' in result.stderr
    assert 'MCP server stopped' in result.stderr
    assert 'Final memory export failed' not in result.stderr
    assert 'secret-test-token' not in result.stderr


def test_token_file_sets_agentic_token_and_token_is_not_logged(tmp_path):
    token_file = tmp_path / 'token.txt'
    token_file.write_text('file-secret-token\n', encoding='utf-8')

    result, call_log = _run_entrypoint(
        tmp_path,
        MCP_SERVER_TOKEN_FILE=str(token_file),
        AGENTIC_TOKEN='old-environment-token',
    )

    assert result.returncode == 0, result.stderr
    assert 'token=file-secret-token' in call_log.read_text(encoding='utf-8')
    assert 'file-secret-token' not in result.stderr
    assert 'old-environment-token' not in result.stderr
    assert f'Loaded AGENTIC_TOKEN from {token_file}' in result.stderr


def test_missing_token_file_is_logged_at_info_and_does_not_fail(tmp_path):
    token_file = tmp_path / 'missing-token.txt'

    result, _call_log = _run_entrypoint(
        tmp_path,
        MCP_SERVER_TOKEN_FILE=str(token_file),
    )

    assert result.returncode == 0, result.stderr
    assert f'INFO MCP_SERVER_TOKEN_FILE does not exist: {token_file}' in result.stderr


def test_wrapper_log_level_is_configurable(tmp_path):
    result, call_log = _run_entrypoint(tmp_path, MCP_SERVER_LOG_LEVEL='ERROR')

    assert result.returncode == 0, result.stderr
    assert 'Container startup environment:' not in result.stderr
    assert 'MCP server started' not in result.stderr
    assert any(line.startswith('server serve ') for line in call_log.read_text().splitlines())


def test_invalid_wrapper_log_level_fails_clearly(tmp_path):
    result, _call_log = _run_entrypoint(tmp_path, MCP_SERVER_LOG_LEVEL='verbose')

    assert result.returncode == 1
    assert 'MCP_SERVER_LOG_LEVEL must be one of:' in result.stderr


def test_token_file_pointing_at_a_directory_fails_with_a_clear_message(tmp_path):
    token_dir = tmp_path / 'token'
    token_dir.mkdir()

    result, _ = _run_entrypoint(tmp_path, MCP_SERVER_TOKEN_FILE=str(token_dir))

    assert result.returncode == 1
    assert f'MCP_SERVER_TOKEN_FILE is not a file: {token_dir}' in result.stderr


def test_empty_environment_values_fall_back_to_defaults(tmp_path):
    result, call_log = _run_entrypoint(
        tmp_path,
        MCP_SERVER_PROTOCOL='',
        MCP_SERVER_HOST='',
        MCP_SERVER_PORT='',
        MCP_SERVER_LOG_LEVEL='',
        RUST_LOG='',
        MCP_SERVER_TOKEN_FILE='',
        AGENTIC_TOKEN='',
        EXPORT_MEMORY_INTERVAL='',
    )

    assert result.returncode == 0, result.stderr
    assert 'server serve ' in call_log.read_text(encoding='utf-8')
    assert 'MCP_SERVER_PROTOCOL=stdio' in result.stderr


def test_missing_import_file_warns_and_starts_with_empty_memory(tmp_path):
    missing = tmp_path / 'memory' / 'memory.amem'

    result, call_log = _run_entrypoint(tmp_path, IMPORT_MEMORY_FILE=str(missing))

    assert result.returncode == 0, result.stderr
    assert f'WARNING No import memory found at {missing}; starting with an empty memory' in (
        result.stderr
    )
    assert 'amem init ' in call_log.read_text(encoding='utf-8')
    assert 'amem import ' not in call_log.read_text(encoding='utf-8')


def test_empty_import_file_warns_and_starts_with_empty_memory(tmp_path):
    empty = tmp_path / 'memory' / 'memory.json'
    empty.parent.mkdir()
    empty.write_text('', encoding='utf-8')

    result, call_log = _run_entrypoint(tmp_path, IMPORT_MEMORY_FILE=str(empty))

    assert result.returncode == 0, result.stderr
    assert f'WARNING Import memory file {empty} is empty; starting with an empty memory' in (
        result.stderr
    )
    assert 'amem import ' not in call_log.read_text(encoding='utf-8')


def test_import_file_with_wrong_suffix_still_fails(tmp_path):
    result, _ = _run_entrypoint(tmp_path, IMPORT_MEMORY_FILE=str(tmp_path / 'memory.txt'))

    assert result.returncode == 1
    assert 'IMPORT_MEMORY_FILE must end in .amem or .json' in result.stderr


def test_log_file_duplicates_wrapper_and_server_stderr(tmp_path):
    log_file = tmp_path / 'logs' / 'nested' / 'server.log'

    result, _ = _run_entrypoint(
        tmp_path,
        MCP_SERVER_LOG_FILE=str(log_file),
        SERVER_STDERR_LINE='server says hello',
    )

    assert result.returncode == 0, result.stderr
    content = log_file.read_text(encoding='utf-8')
    assert f'Duplicating log output to {log_file}' in content
    assert 'server says hello' in content
    assert 'MCP server stopped' in content
    assert 'server says hello' in result.stderr
    assert f'Duplicating log output to {log_file}' in result.stderr


def test_unwritable_log_file_warns_and_does_not_fail(tmp_path):
    blocker = tmp_path / 'blocker'
    blocker.write_text('', encoding='utf-8')
    log_file = blocker / 'server.log'

    result, _ = _run_entrypoint(tmp_path, MCP_SERVER_LOG_FILE=str(log_file))

    assert result.returncode == 0, result.stderr
    assert f'WARNING Cannot write MCP_SERVER_LOG_FILE {log_file}' in result.stderr
