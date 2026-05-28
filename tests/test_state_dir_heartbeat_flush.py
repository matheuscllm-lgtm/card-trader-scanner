#!/usr/bin/env python3
"""PR-F (2026-05-28) tests — --state-dir + heartbeat + flush per-listing + skip-list TTL.

Cobre o patch arquitetural F do CT scanner v2.11:
  1. resolve_state_dir: explícito (--state-dir) vence; senão LOCALAPPDATA;
     senão SCRIPT_DIR (fallback).
  2. Cache(db_path=tmp) cria o DB em tmp, NÃO em SCRIPT_DIR (testa a armadilha
     do default-arg `db_path=CACHE_DB` bindado no import).
  3. CheckpointWriter.write_progress 3× → reabre, 3 linhas _type=set_progress.
  4. touch_heartbeat → arquivo existe, conteúdo tem timestamp, mtime atualiza.
  5. skip-list TTL: per_set_timeout_ com added_at 8d atrás → expira (dropada);
     unexpected_error_ → permanente; entry legada (str pura) → permanente.

Roda de dois jeitos:
    pytest tests/test_state_dir_heartbeat_flush.py -v
    python tests/test_state_dir_heartbeat_flush.py          # fallback standalone

O segundo modo existe porque o repo historicamente usa testes standalone
(scripts/test_*.py) — não depende de pytest estar instalado.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Repo root no sys.path (tests/ → ..)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cardtrader_scanner as sc  # noqa: E402
from cardtrader_scanner import (  # noqa: E402
    Cache,
    CheckpointWriter,
    resolve_state_dir,
    _skip_entry_is_expired,
    _skip_reason_str,
)


# ──────────────────────────────────────────────────────────────────────
# 1. resolve_state_dir
# ──────────────────────────────────────────────────────────────────────
def test_resolve_state_dir_explicit(tmp_path):
    """--state-dir explícito vence tudo."""
    explicit = tmp_path / "my_state"
    got = resolve_state_dir(explicit)
    assert got == explicit, f"explicit deve vencer; got {got}"


def test_resolve_state_dir_default_localappdata(tmp_path, monkeypatch):
    """Sem --state-dir mas com LOCALAPPDATA → <LOCALAPPDATA>/CardTraderScanner."""
    fake_lad = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(fake_lad))
    got = resolve_state_dir(None)
    assert got == fake_lad / "CardTraderScanner", f"got {got}"


def test_resolve_state_dir_fallback_script_dir(monkeypatch):
    """Sem --state-dir e sem LOCALAPPDATA → fallback SCRIPT_DIR (legado)."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    got = resolve_state_dir(None)
    assert got == sc.SCRIPT_DIR, f"fallback deve ser SCRIPT_DIR; got {got}"


def test_state_dir_derived_paths(tmp_path):
    """cache/skip/heartbeat/checkpoint derivam do state_dir; XLSX (output) não."""
    state_dir = resolve_state_dir(tmp_path / "st")
    cache_db = state_dir / "cache.db"
    skip = state_dir / "scanner_skip_list.json"
    heartbeat = state_dir / "heartbeat.txt"
    # checkpoint deriva do NOME do output, mas vive no state_dir
    out_path = Path("/some/drive/dir/weekly_2026-05-28.xlsx")
    checkpoint = state_dir / (out_path.name + ".checkpoint.jsonl")

    assert cache_db.parent == state_dir
    assert skip.parent == state_dir
    assert heartbeat.parent == state_dir
    assert checkpoint.parent == state_dir
    assert checkpoint.name == "weekly_2026-05-28.xlsx.checkpoint.jsonl"
    # XLSX final NÃO está no state_dir (continua no caminho de --output)
    assert out_path.parent != state_dir


# ──────────────────────────────────────────────────────────────────────
# 2. Cache default-arg trap
# ──────────────────────────────────────────────────────────────────────
def test_cache_db_path_explicit_lands_in_tmp(tmp_path):
    """Cache(db_path=tmp) deve criar o DB em tmp, não em SCRIPT_DIR.

    Garante que passar db_path explícito contorna a armadilha do default-arg
    `db_path=CACHE_DB` (bindado no import). Também confirma que o arquivo
    cache.db NÃO apareceu no SCRIPT_DIR como efeito colateral.
    """
    db_path = tmp_path / "cache.db"
    script_dir_db = sc.SCRIPT_DIR / "cache.db"
    script_dir_db_existed_before = script_dir_db.exists()

    c = Cache(db_path=db_path)
    try:
        assert db_path.exists(), f"DB deveria existir em {db_path}"
    finally:
        c.db.close()  # libera handle SQLite (Windows: senão tmp cleanup falha)

    # Não criou cache.db no SCRIPT_DIR como efeito colateral
    if not script_dir_db_existed_before:
        assert not script_dir_db.exists(), (
            f"Cache(db_path=tmp) NÃO deveria ter criado {script_dir_db}"
        )


# ──────────────────────────────────────────────────────────────────────
# 3. CheckpointWriter.write_progress
# ──────────────────────────────────────────────────────────────────────
def test_write_progress_emits_set_progress_lines(tmp_path):
    """3× write_progress → reabrir o JSONL e achar exatamente 3 set_progress."""
    cp_path = tmp_path / "out.xlsx.checkpoint.jsonl"
    cw = CheckpointWriter(cp_path, every_n=10, heartbeat_path=tmp_path / "hb.txt")
    try:
        cw.write_progress("sfa", 50, 200)
        cw.write_progress("sfa", 100, 200)
        cw.write_progress("sfa", 150, 200)
    finally:
        cw.close()

    lines = [json.loads(l) for l in cp_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    progress = [l for l in lines if l.get("_type") == "set_progress"]
    assert len(progress) == 3, f"esperava 3 set_progress, achou {len(progress)}: {lines}"
    assert all(p["set_code"] == "sfa" for p in progress)
    assert [p["i"] for p in progress] == [50, 100, 150]
    assert all(p["total"] == 200 for p in progress)
    assert all("stamp" in p for p in progress)


def test_write_progress_noop_when_disabled(tmp_path):
    """every_n=0 → checkpoint desabilitado → write_progress não cria arquivo."""
    cp_path = tmp_path / "disabled.checkpoint.jsonl"
    cw = CheckpointWriter(cp_path, every_n=0, heartbeat_path=tmp_path / "hb.txt")
    cw.write_progress("sfa", 50, 200)
    cw.close()
    assert not cp_path.exists(), "checkpoint desabilitado não deveria escrever"


# ──────────────────────────────────────────────────────────────────────
# 4. touch_heartbeat
# ──────────────────────────────────────────────────────────────────────
def test_touch_heartbeat_writes_timestamp_and_updates_mtime(tmp_path):
    """touch_heartbeat cria arquivo com timestamp+nota; segunda chamada atualiza mtime."""
    hb_path = tmp_path / "heartbeat.txt"
    cw = CheckpointWriter(tmp_path / "out.checkpoint.jsonl", every_n=10, heartbeat_path=hb_path)
    try:
        cw.touch_heartbeat("set 1/10 (sfa)")
        assert hb_path.exists(), "heartbeat.txt deveria existir"
        content1 = hb_path.read_text(encoding="utf-8")
        # tab-separated: <iso_ts>\t<note>
        assert "\t" in content1
        ts_part, note_part = content1.rstrip("\n").split("\t", 1)
        # timestamp parseável como ISO
        parsed = datetime.fromisoformat(ts_part)
        assert parsed is not None
        assert note_part == "set 1/10 (sfa)"
        mtime1 = hb_path.stat().st_mtime_ns

        time.sleep(0.05)
        cw.touch_heartbeat("set 2/10 (svp)")
        mtime2 = hb_path.stat().st_mtime_ns
        content2 = hb_path.read_text(encoding="utf-8")
        # modo "w" → sobrescreve (não append): só 1 linha
        assert content2.count("\n") == 1, f"heartbeat deveria ter 1 linha, got {content2!r}"
        assert "set 2/10 (svp)" in content2
        assert mtime2 >= mtime1, "mtime deveria atualizar (ou ao menos não regredir)"
    finally:
        cw.close()


def test_touch_heartbeat_noop_without_path():
    """Sem heartbeat_path, touch_heartbeat é no-op silencioso (não levanta)."""
    cw = CheckpointWriter(Path("nonexistent_dir_xyz/out.jsonl"), every_n=0, heartbeat_path=None)
    cw.touch_heartbeat("whatever")  # não deve levantar
    cw.close()


# ──────────────────────────────────────────────────────────────────────
# 5. skip-list TTL
# ──────────────────────────────────────────────────────────────────────
def _iso_days_ago(days: float) -> str:
    ts = datetime.now(timezone.utc) - timedelta(days=days)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_skip_ttl_transient_expired_is_dropped():
    """per_set_timeout_ com added_at 8d atrás → expira."""
    entry = {"reason": "per_set_timeout_120s_at_30_of_400", "added_at": _iso_days_ago(8)}
    assert _skip_entry_is_expired(entry) is True


def test_skip_ttl_transient_fresh_persists():
    """per_set_timeout_ com added_at 1d atrás → ainda dentro do TTL (não expira)."""
    entry = {"reason": "per_set_timeout_120s_at_30_of_400", "added_at": _iso_days_ago(1)}
    assert _skip_entry_is_expired(entry) is False


def test_skip_ttl_mass_pricing_failure_expired():
    """mass_pricing_failure_ também é transiente → expira após TTL."""
    entry = {"reason": "mass_pricing_failure_60_of_100", "added_at": _iso_days_ago(8)}
    assert _skip_entry_is_expired(entry) is True


def test_skip_ttl_unexpected_error_permanent():
    """unexpected_error_ é PERMANENTE → nunca expira, mesmo 8d atrás."""
    entry = {"reason": "unexpected_error_KeyError", "added_at": _iso_days_ago(8)}
    assert _skip_entry_is_expired(entry) is False


def test_skip_ttl_legacy_str_permanent():
    """Entry legada (str pura, sem added_at) → tratada como permanente."""
    legacy = "per_set_timeout_120s_at_30_of_400"  # str, prefixo transiente
    assert _skip_entry_is_expired(legacy) is False
    # E _skip_reason_str normaliza
    assert _skip_reason_str(legacy) == legacy


def test_skip_ttl_dict_without_added_at_permanent():
    """dict transiente sem added_at → conservador: não dropa."""
    entry = {"reason": "per_set_timeout_120s"}  # sem added_at
    assert _skip_entry_is_expired(entry) is False


def test_skip_ttl_corrupt_added_at_permanent():
    """added_at corrompido → não dropa (conservador)."""
    entry = {"reason": "per_set_timeout_120s", "added_at": "not-a-date"}
    assert _skip_entry_is_expired(entry) is False


def test_skip_reason_str_handles_dict_and_str_and_none():
    assert _skip_reason_str({"reason": "x", "added_at": "y"}) == "x"
    assert _skip_reason_str("legacy") == "legacy"
    assert _skip_reason_str(None) == ""


# ──────────────────────────────────────────────────────────────────────
# Standalone runner (sem pytest)
# ──────────────────────────────────────────────────────────────────────
class _TmpPath:
    """Mínimo stand-in pra fixture tmp_path quando rodando standalone."""
    def __init__(self, base: Path):
        self._base = base


class _MonkeyPatch:
    """Mínimo stand-in pra fixture monkeypatch (set/delenv) com restore."""
    def __init__(self):
        self._saved: list[tuple[str, object]] = []

    def setenv(self, k, v):
        self._saved.append((k, os.environ.get(k)))
        os.environ[k] = v

    def delenv(self, k, raising=True):
        self._saved.append((k, os.environ.get(k)))
        os.environ.pop(k, None)

    def undo(self):
        for k, old in reversed(self._saved):
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        self._saved.clear()


def _standalone_main() -> int:
    import inspect
    import tempfile

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
            tmpdir = tempfile.mkdtemp(prefix="ct_pr_f_test_")
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
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_standalone_main())
