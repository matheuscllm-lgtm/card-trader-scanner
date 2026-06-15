#!/usr/bin/env python3
"""Test (robustez 2026-06-15 — candidato 2): run-guard contra instâncias
concorrentes no mesmo state-dir.

Incidente: dois scanners no mesmo cache.db/skip-list disputam lock SQLite →
pricing despenca pra ~9s/listing → per-set-timeout estoura por falsa lentidão
→ skip-list é ENVENENADA. O guard segura um lock exclusivo no state-dir.

Verifica:
  - 1ª aquisição → handle não-None
  - 2ª aquisição no MESMO dir (com a 1ª ainda viva) → None (recusa)
  - após release da 1ª → re-aquisição volta a funcionar
  - state-dirs DIFERENTES → ambos adquirem (não conflitam)
  - lockfile grava pid pra diagnóstico

NOTA Windows: a limpeza dos diretórios temp é best-effort (shutil.rmtree
ignore_errors) — o handle do lock é fechado por .release(), mas o Windows
às vezes segura o arquivo por uma fração de segundo (AV/indexador). Isso é
artefato do filesystem de TESTE, não do produto.

Usage:
    python scripts/test_run_guard.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from cardtrader_scanner import acquire_run_guard  # noqa: E402


def _mkdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="ct_runguard_"))


def _rmdir(d: Path) -> None:
    shutil.rmtree(d, ignore_errors=True)


def test_second_acquire_same_dir_refused():
    print("\n[test_second_acquire_same_dir_refused]")
    d = _mkdir()
    try:
        g1 = acquire_run_guard(d)
        assert g1 is not None, "1ª aquisição deve ter sucesso"
        g2 = acquire_run_guard(d)
        assert g2 is None, "2ª aquisição no mesmo dir (1ª viva) deve ser recusada"
        g1.release()
        print("  PASS")
    finally:
        _rmdir(d)


def test_release_allows_reacquire():
    print("\n[test_release_allows_reacquire]")
    d = _mkdir()
    try:
        g1 = acquire_run_guard(d)
        assert g1 is not None
        g1.release()
        g2 = acquire_run_guard(d)
        assert g2 is not None, "após release, re-aquisição deve funcionar"
        g2.release()
        print("  PASS")
    finally:
        _rmdir(d)


def test_different_dirs_dont_conflict():
    print("\n[test_different_dirs_dont_conflict]")
    d1, d2 = _mkdir(), _mkdir()
    try:
        g1 = acquire_run_guard(d1)
        g2 = acquire_run_guard(d2)
        assert g1 is not None and g2 is not None, \
            "state-dirs diferentes não devem conflitar"
        g1.release()
        g2.release()
        print("  PASS")
    finally:
        _rmdir(d1)
        _rmdir(d2)


def test_lockfile_records_pid():
    print("\n[test_lockfile_records_pid]")
    import os
    d = _mkdir()
    try:
        g = acquire_run_guard(d)
        assert g is not None
        # Em Windows o lockfile está com LOCK_EX → outro open (read_text) é
        # negado. Liberamos primeiro e lemos depois: valida que o PID foi
        # gravado no acquire (o conteúdo persiste após release).
        g.release()
        content = (d / "scanner_run.lock").read_text(encoding="utf-8")
        assert f"pid={os.getpid()}" in content, \
            f"lockfile deve gravar pid; got: {content!r}"
        print("  PASS")
    finally:
        _rmdir(d)


def main() -> int:
    failed = 0
    for fn in (
        test_second_acquire_same_dir_refused,
        test_release_allows_reacquire,
        test_different_dirs_dont_conflict,
        test_lockfile_records_pid,
    ):
        try:
            fn()
        except AssertionError as e:
            print(f"  ASSERTION FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    if failed:
        print(f"\nFAIL: {failed} test(s) failed")
        return 1
    print(f"\nPASS: all run-guard tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
