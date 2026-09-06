"""Reference price cells for the canonical chat delivery; no network calls."""
from urllib.parse import quote, urlsplit

def reference_price(label, url):
    text = str(label if label is not None else '—')
    if text.strip() in {'', '—', '-', 'pendente', 'None', 'nan'}:
        return text or '—'
    try:
        parsed = urlsplit(str(url or ''))
        valid = parsed.scheme in {'http', 'https'} and bool(parsed.hostname)
    except ValueError:
        valid = False
    if not valid:
        return text + ' (sem link de referência)'
    return '[' + text + '](' + quote(str(url), safe='%/?&=:+,*') + ')'
