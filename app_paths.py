"""Explicit, EXE-relative portable data storage; no source/CI side effects.

No configuration means the caller keeps its established AppData policy. A
present but invalid configuration is an error, never an implicit new store.
The sector store still validates the data directory and its reparse ancestry.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
import json
import stat
import sys
import tempfile

from common import AuditError

CONFIG_FILE = 'portable-config.json'
SCHEMA_VERSION = 1
MAX_CONFIG_BYTES = 16_384


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate configuration key')
        value[key] = item
    return value


def _read_config(path):
    try:
        attributes = path.stat(follow_symlinks=False)
        if path.is_symlink() or getattr(attributes, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise AuditError('이식형 설정 파일은 연결 파일 대신 EXE 옆의 독립된 파일을 사용하세요.')
        if not path.is_file() or not 0 < attributes.st_size <= MAX_CONFIG_BYTES:
            raise AuditError('이식형 설정 파일의 종류 또는 크기가 올바르지 않습니다.')
        config = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuditError('EXE 옆 이식형 설정을 읽을 수 없습니다. portable-config.json을 확인하세요.') from exc
    if (not isinstance(config, dict) or set(config) != {'schema_version', 'data_directory'}
            or type(config['schema_version']) is not int or config['schema_version'] != SCHEMA_VERSION):
        raise AuditError('지원하지 않는 이식형 설정 형식입니다. schema_version 1과 data_directory가 필요합니다.')
    return config


def _relative_target(exe_dir, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
            or any(ord(char) < 32 for char in relative)
            or relative.startswith('/') or PureWindowsPath(relative).drive):
        raise AuditError('이식형 데이터 경로는 EXE 기준의 상대경로여야 합니다.')
    parts = relative.split('/')
    if any(not part or part == '.' or (part != '..' and part.endswith((' ', '.'))) for part in parts):
        raise AuditError('이식형 데이터 상대경로 형식이 올바르지 않습니다.')
    # One explicit parent step supports 실행파일/ -> 데이터/회사별업무.
    # Further parent steps and all embedded parent steps are rejected lexically.
    if '..' in parts and not (parts[0] == '..' and parts.count('..') == 1 and len(parts) > 1):
        raise AuditError('이식형 데이터 경로는 프로그램 폴더 밖으로 나갈 수 없습니다.')
    if any(part == '..' for part in parts[1:]):
        raise AuditError('이식형 데이터 경로의 중간 상위 폴더 참조는 허용하지 않습니다.')
    # A parent component is the sole intentional exception to trailing-dot rules.
    normalized_parts = PurePosixPath(relative).parts
    app_root = exe_dir.parent.resolve()
    target = exe_dir.joinpath(*normalized_parts).resolve()
    if target == app_root or target == exe_dir.resolve() or not target.is_relative_to(app_root):
        raise AuditError('이식형 데이터 폴더는 프로그램 루트 안의 별도 하위 폴더여야 합니다.')
    if target.exists() and not target.is_dir():
        raise AuditError('이식형 데이터 경로에 폴더가 아닌 파일이 있습니다.')
    return target


def _check_writable(exe_dir):
    # os.access does not reliably reflect Windows directory ACLs. Ask the OS
    # with an automatically removed, empty temporary file; never alter a source.
    try:
        with tempfile.TemporaryFile(prefix='.js-audit-write-check-', dir=exe_dir):
            pass
    except OSError as exc:
        raise AuditError('EXE 폴더에 쓰기 권한이 없습니다. 통합감사 프로그램 폴더를 쓰기 가능한 위치로 옮기세요.') from exc


def portable_storage_root(*, executable=None, frozen=None):
    """Return a validated configured Path, otherwise None for legacy AppData.

    Production callers pass no arguments. Explicit arguments are for isolated
    tests only. Source execution always returns None, even beside a config.
    This resolves paths independently of CWD and never creates a data store.
    """
    if not (bool(getattr(sys, 'frozen', False)) if frozen is None else bool(frozen)):
        return None
    exe_dir = Path(sys.executable if executable is None else executable).absolute().parent
    config_path = exe_dir / CONFIG_FILE
    if not config_path.exists() and not config_path.is_symlink():
        return None
    config = _read_config(config_path)
    try:
        target = _relative_target(exe_dir, config['data_directory'])
    except OSError as exc:
        raise AuditError('이식형 데이터 폴더 경로를 확인하지 못했습니다.') from exc
    _check_writable(exe_dir)
    return target
