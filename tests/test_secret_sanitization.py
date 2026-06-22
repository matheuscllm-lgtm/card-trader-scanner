"""Regressao: segredos (CT_JWT / POKEMONTCG_API_KEY) com BOM/zero-width.

Bug observado no GitHub Actions (run 27925489942): o secret POKEMONTCG_API_KEY
tinha um BOM (U+FEFF) na frente. Headers HTTP sao codificados em latin-1 pelo
`requests`, entao o valor "\\ufeff..." virava
`UnicodeEncodeError: 'latin-1' codec can't encode '\\ufeff'` em TODA chamada de
pricing -> mass pricing failure 20/20 -> set abortado -> 0 oportunidades, mesmo
com o workflow "verde".

`str.strip()` NAO remove BOM (U+FEFF nao e whitespace pra Python), entao a
sanitizacao tem de ser explicita. `_clean_secret` cobre isso e estes testes
travam o comportamento.

NB: usamos escapes "\\ufeff"/"\\u200b" de proposito (nada de caracteres
invisiveis literais no fonte do teste).

Roda via pytest E standalone (python tests/test_secret_sanitization.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cardtrader_scanner as cs

BOM = "\ufeff"
ZWSP = "\u200b"


# ─── _clean_secret puro ───────────────────────────────────────────────────────

def test_clean_secret_strips_bom():
    assert cs._clean_secret(BOM + "abc123") == "abc123"


def test_clean_secret_strips_zero_width_space():
    assert cs._clean_secret(ZWSP + "abc123") == "abc123"


def test_clean_secret_strips_surrounding_whitespace_and_newline():
    assert cs._clean_secret("  abc123\n") == "abc123"


def test_clean_secret_combo_bom_plus_whitespace():
    assert cs._clean_secret(BOM + "  abc123  \n") == "abc123"


def test_clean_secret_none_and_empty_return_none():
    assert cs._clean_secret(None) is None
    assert cs._clean_secret("") is None
    assert cs._clean_secret("   ") is None
    # BOM-only / zero-width-only viram None (nao viram header invalido)
    assert cs._clean_secret(BOM) is None
    assert cs._clean_secret(ZWSP + BOM) is None


def test_clean_secret_preserves_clean_value():
    assert cs._clean_secret("eyJhbGciOi.token.sig") == "eyJhbGciOi.token.sig"


# ─── Regressao real: header tem de ser latin-1-encodavel ──────────────────────

def test_pokemontcg_header_is_latin1_encodable_with_bom_key():
    prov = cs.PokemonTcgIoProvider(BOM + "secretkey", cache=None)
    hdr = prov.session.headers["X-Api-Key"]
    # Antes do fix isto explodia ao montar o request; aqui garantimos que o
    # valor ja esta limpo e codifica em latin-1 (o que o requests faz).
    hdr.encode("latin-1")
    assert hdr == "secretkey"


def test_pokemontcg_bom_only_key_sets_no_header():
    # Key que era so BOM vira None -> nao adiciona header (fallback sem-key,
    # que funciona no pokemontcg.io).
    prov = cs.PokemonTcgIoProvider(BOM, cache=None)
    assert "X-Api-Key" not in prov.session.headers


def test_cardtrader_authorization_header_clean_with_bom_jwt():
    c = cs.CardTraderClient(BOM + "JWT.tok.en")
    auth = c.session.headers["Authorization"]
    auth.encode("latin-1")
    assert auth == "Bearer JWT.tok.en"


def test_cardtrader_bom_only_jwt_raises():
    raised = False
    try:
        cs.CardTraderClient(BOM)
    except ValueError:
        raised = True
    assert raised, "CT_JWT so-BOM deveria virar None e levantar ValueError"


if __name__ == "__main__":
    # Runner standalone (sem pytest): executa cada test_* e reporta.
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passaram")
    sys.exit(1 if failed else 0)
