#!/usr/bin/env python3
"""PR-G (2026-05-29) tests — skip-list robusta a BOM UTF-8.

Cobre o fix do crash pré-set-1: quando a skip-list JSON é reescrita por
`Set-Content -Encoding utf8` (PS 5.1) ou vários editores, ela ganha um BOM
UTF-8 (EF BB BF). `json.loads` puro rejeita BOM com
"JSONDecodeError: Unexpected UTF-8 BOM" e o scan crasha antes do set 1
(LAST_RESULT=1, ~2s). Já quebrou um daily 2026-05-29.

O fix troca `read_text(encoding="utf-8")` por `encoding="utf-8-sig"` em
`_read_skip_file_locked`, que remove o BOM se presente e é idêntico ao
utf-8 quando não há BOM.

Testa dois níveis:
  - `_read_skip_file_locked` direto (a função com o fix).
  - `load_skip_list` (caller público, com lock portalocker + sidecar .lock)
    pra provar que o caminho end-to-end também tolera BOM.

Roda de dois jeitos (espelha test_state_dir_heartbeat_flush.py):
    pytest tests/test_skiplist_bom.py -v
    python tests/test_skiplist_bom.py          # fallback standalone
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Repo root no sys.path (tests/ → ..)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import (  # noqa: E402
    _read_skip_file_locked,
    load_skip_list,
)

_BOM = b"\xef\xbb\xbf"
_PAYLOAD = b'{"skipped":["xyz"],"reasons":{}}'


def _point_skip_file_at(monkeypatch, path: Path) -> None:
    """Reaponta o global SKIP_LIST_FILE pra o tmp (lido dinamicamente nas funções)."""
    monkeypatch.setattr(sc, "SKIP_LIST_FILE", path)


# ──────────────────────────────────────────────────────────────────────
# 1. _read_skip_file_locked direto (a função patcheada)
# ──────────────────────────────────────────────────────────────────────
def test_read_skip_file_with_bom_parses_ok(tmp_path, monkeypatch):
    """JSON COM BOM UTF-8 → parseia OK (era o crash). skipped contém 'xyz'."""
    p = tmp_path / "scanner_skip_list.json"
    p.write_bytes(_BOM + _PAYLOAD)
    _point_skip_file_at(monkeypatch, p)

    got = _read_skip_file_locked()
    assert got["skipped"] == ["xyz"], f"esperava ['xyz'], got {got.get('skipped')!r}"
    assert got["reasons"] == {}


def test_read_skip_file_without_bom_still_parses(tmp_path, monkeypatch):
    """Não-regressão: JSON SEM BOM continua parseando idêntico."""
    p = tmp_path / "scanner_skip_list.json"
    p.write_bytes(_PAYLOAD)  # sem BOM
    _point_skip_file_at(monkeypatch, p)

    got = _read_skip_file_locked()
    assert got["skipped"] == ["xyz"], f"esperava ['xyz'], got {got.get('skipped')!r}"
    assert got["reasons"] == {}


def test_read_skip_file_invalid_json_still_raises(tmp_path, monkeypatch):
    """Não-regressão: JSON inválido continua levantando JSONDecodeError
    (o tratamento de erro existente em load_skip_list/run_scan depende disso)."""
    p = tmp_path / "scanner_skip_list.json"
    p.write_bytes(b'{"skipped": [unclosed')  # JSON quebrado
    _point_skip_file_at(monkeypatch, p)

    raised = False
    try:
        _read_skip_file_locked()
    except json.JSONDecodeError:
        raised = True
    assert raised, "JSON inválido deveria propagar JSONDecodeError"


def test_read_skip_file_invalid_json_with_bom_still_raises(tmp_path, monkeypatch):
    """JSON inválido COM BOM: utf-8-sig remove BOM mas o conteúdo continua
    quebrado → ainda JSONDecodeError (não mascara erro real de conteúdo)."""
    p = tmp_path / "scanner_skip_list.json"
    p.write_bytes(_BOM + b'{"skipped": [unclosed')
    _point_skip_file_at(monkeypatch, p)

    raised = False
    try:
        _read_skip_file_locked()
    except json.JSONDecodeError:
        raised = True
    assert raised, "JSON inválido (mesmo com BOM) deveria propagar JSONDecodeError"


def test_read_skip_file_missing_returns_empty(tmp_path, monkeypatch):
    """Não-regressão: arquivo inexistente → payload vazio (não levanta)."""
    p = tmp_path / "does_not_exist.json"
    _point_skip_file_at(monkeypatch, p)

    got = _read_skip_file_locked()
    assert got["skipped"] == []
    assert got["reasons"] == {}


# ──────────────────────────────────────────────────────────────────────
# 2. load_skip_list (caller público, com lock portalocker)
# ──────────────────────────────────────────────────────────────────────
def test_load_skip_list_with_bom_end_to_end(tmp_path, monkeypatch):
    """Caminho real (com shared lock + sidecar .lock): BOM → parseia OK.
    Prova que o fix vale pro fluxo que run_scan de fato usa."""
    p = tmp_path / "scanner_skip_list.json"
    p.write_bytes(_BOM + _PAYLOAD)
    _point_skip_file_at(monkeypatch, p)

    got = load_skip_list()
    assert got["skipped"] == ["xyz"], f"esperava ['xyz'], got {got.get('skipped')!r}"


# ──────────────────────────────────────────────────────────────────────
# Standalone runner (sem pytest) — espelha test_state_dir_heartbeat_flush.py
# ──────────────────────────────────────────────────────────────────────
class _MonkeyPatch:
    """Mínimo stand-in pra fixture monkeypatch (setattr) com restore."""
    _SENTINEL = object()

    def __init__(self):
        self._saved: list[tuple[object, str, object]] = []

    def setattr(self, target, name, value):
        old = getattr(target, name, self._SENTINEL)
        self._saved.append((target, name, old))
        setattr(target, name, value)

    def setenv(self, k, v):
        self._saved.append((os.environ, k, os.environ.get(k, self._SENTINEL)))
        os.environ[k] = v

    def undo(self):
        for target, name, old in reversed(self._saved):
            if target is os.environ:
                if old is self._SENTINEL:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = old
            else:
                if old is self._SENTINEL:
                    delattr(target, name)
                else:
                    setattr(target, name, old)
        self._saved.clear()


def _standalone_main() -> int:
    import inspect
    import shutil

    tests = [obj for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    failed = 0
    passed = 0
    for fn in tests:
        sig = inspect.signature(fn)
        kwargs = {}
        tmpdir = None
        mp = None
        if "tmp_path" in sig.parameters:
            tmpdir = tempfile.mkdtemp(prefix="ct_pr_g_test_")
            kwargs["tmp_path"] = Path(tmpdir)
        if "monkeypatch" in sig.parameters:
            mp = _MonkeyPatch()
            kwargs["monkeypatch"] = mp
        try:
            fn(**kwargs)
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            if mp is not None:
                mp.undo()
            if tmpdir is not None:
                shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_standalone_main())
