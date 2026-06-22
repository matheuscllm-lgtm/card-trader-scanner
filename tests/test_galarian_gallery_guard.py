"""Galarian Gallery (GG##) false-positive guard.

Production guarded only Trainer Gallery (TG##, ^TG\\d+); the structurally
identical Galarian Gallery subset (GG##, SWSH era — Brilliant Stars / Astral
Radiance / Lost Origin / Silver Tempest / Crown Zenith) has the SAME pokemontcg.io
reference-price inflation but was NOT guarded, so GG## cards slipped through as a
COMPRA with a fake margin.

Found via ASI-Evolve (experiment cardtrader_classify): the baseline COMPRA-F1 was
0.7273, with the GG## rows as the only false positives; generalising the gallery
regex to `^(?:TG|GG)\\d+` took it to 1.0. This test pins that fix.

Conservative by construction: GG## is routed to NAO / manual review exactly like
TG## — it can never create an auto-buy.

Runs via pytest AND standalone (python tests/test_galarian_gallery_guard.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cardtrader_postprocess as pp
import cardtrader_scanner as cs


def test_gallery_regex_covers_tg_and_gg():
    re_ = pp.TRAINER_GALLERY_RE
    # Both gallery subsets match, case-insensitively.
    assert re_.match("TG12")
    assert re_.match("GG67")
    assert re_.match("gg09")
    assert re_.match("Gg7")
    # Plain numbers and alpha-suffix variants must NOT be treated as gallery.
    assert not re_.match("199")
    assert not re_.match("091a")   # alpha-suffix promo/League variant (own path)
    assert not re_.match("GG")     # needs a number
    assert not re_.match("EGG12")  # must anchor at start


def test_scanner_regex_skips_tg_and_gg_at_scan_time():
    """Scanner-level defense in depth: _TRAINER_GALLERY_RE skips both TG## and GG##.

    Previously only TG## was skipped at scan time; GG## listings reached the
    pricing calls and were only caught downstream in postprocess. Both subsets
    inflate the pokemontcg.io reference 5-10x, so they should be dropped before
    pricing — exactly like _passes_filters does via this regex.
    """
    re_ = cs._TRAINER_GALLERY_RE
    # Both gallery subsets are skipped at scan time, case-insensitively.
    assert re_.match("TG12")
    assert re_.match("GG12")
    assert re_.match("gg09")
    assert re_.match("Gg7")
    # Plain numbers and anchored non-gallery strings are NOT skipped.
    assert not re_.match("199")
    assert not re_.match("GG")     # needs a number
    assert not re_.match("EGG12")  # must anchor at start
    # Scanner and postprocess gallery regexes stay in lockstep (same coverage).
    for num in ("TG12", "GG44", "gg09", "199", "091a", "EGG12", "GG"):
        assert bool(re_.match(num)) == bool(pp.TRAINER_GALLERY_RE.match(num)), num


def _gallery_flag(card_number):
    """Reproduce the upstream df mask that sets trainer_gallery_potential_fp."""
    return bool(pp.TRAINER_GALLERY_RE.match(str(card_number)))


def test_classify_gg_routes_to_nao():
    """A tempting high-margin GG## card must be NAO, not COMPRA."""
    cfg = pp.DecisionConfig()
    row = {
        "card_number": "GG44",
        "trainer_gallery_potential_fp": _gallery_flag("GG44"),
        "chase_tier": "TOP",
        "net_margin": 0.55,
        "lucro_liq": 260.0,
        "validation_status": "VALIDATED_REAL",
    }
    decision, reason = pp.classify_decision(row, cfg)
    assert decision == "NAO", f"GG## deveria ser NAO, veio {decision} ({reason})"
    assert "GG" in reason or "gallery" in reason.lower()


def test_classify_tg_still_nao():
    """Regression: TG## behaviour is unchanged."""
    cfg = pp.DecisionConfig()
    row = {
        "card_number": "TG12",
        "trainer_gallery_potential_fp": _gallery_flag("TG12"),
        "chase_tier": "TOP",
        "net_margin": 0.60,
        "lucro_liq": 300.0,
        "validation_status": "VALIDATED_REAL",
    }
    decision, _ = pp.classify_decision(row, cfg)
    assert decision == "NAO"


def test_classify_plain_card_unaffected():
    """A clean non-gallery card with a real margin still reaches COMPRA."""
    cfg = pp.DecisionConfig()
    row = {
        "card_number": "199",
        "trainer_gallery_potential_fp": _gallery_flag("199"),
        "chase_tier": "TOP",
        "net_margin": 0.35,
        "lucro_liq": 140.0,
        "validation_status": "VALIDATED_REAL",
    }
    decision, _ = pp.classify_decision(row, cfg)
    assert decision == "COMPRA"


if __name__ == "__main__":
    test_gallery_regex_covers_tg_and_gg()
    test_classify_gg_routes_to_nao()
    test_classify_tg_still_nao()
    test_classify_plain_card_unaffected()
    print("OK — Galarian Gallery guard tests pass")
