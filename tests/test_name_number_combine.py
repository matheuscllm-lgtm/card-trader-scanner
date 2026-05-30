"""PR-I + PR-K: card name + number combinados na célula 'Carta'.

PR-K (2026-05-29) atualizou o formato pra MYP-style com parens:
  - Com set_code mapeado: "Plusle (193/197)"
  - Sem set_code mapeado ou sem coluna: "Plusle (193)"

Estes testes cobrem o caso SEM coluna set_code (fallback "(NNN)").
Casos com set_code mapeado ficam em test_ct_myp_model.py.

Roda via pytest E standalone (python tests/test_name_number_combine.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cardtrader_postprocess as pp


def test_combine_numeric_no_set():
    """Sem set_code → 'Nome (NNN)' sem total."""
    df = pd.DataFrame({"card_name": ["Minccino"], "card_number": [182]})
    out = pp._combine_name_number(df)
    assert out["card_name"].iloc[0] == "Minccino (182)"
    assert out["card_number"].iloc[0] == 182  # Nº preservado separado


def test_combine_float_strips_dot_zero():
    df = pd.DataFrame({"card_name": ["Plusle"], "card_number": [193.0]})
    assert pp._combine_name_number(df)["card_name"].iloc[0] == "Plusle (193)"


def test_combine_missing_number_none():
    df = pd.DataFrame({"card_name": ["Mew"], "card_number": [None]})
    assert pp._combine_name_number(df)["card_name"].iloc[0] == "Mew"


def test_combine_nan():
    df = pd.DataFrame({"card_name": ["X"], "card_number": [float("nan")]})
    assert pp._combine_name_number(df)["card_name"].iloc[0] == "X"


def test_combine_alphanumeric_number():
    df = pd.DataFrame({"card_name": ["Pikachu"], "card_number": ["SV161"]})
    assert pp._combine_name_number(df)["card_name"].iloc[0] == "Pikachu (SV161)"


def test_no_columns_is_noop():
    df = pd.DataFrame({"foo": [1]})
    assert list(pp._combine_name_number(df).columns) == ["foo"]


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"PASS {fn.__name__}")
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
