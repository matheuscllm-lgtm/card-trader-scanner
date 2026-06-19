# price-compare-tool

A small personal Python utility that compares item prices between two public
reference sources and reports notable differences to a spreadsheet. It is a
single-user hobby project; there is no hosted service, no website and no support.

## Requirements

- Python 3.12+
- Dependencies in `requirements.txt`

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Copy the template and fill in your own values
cp .env.example .env      # (copy .env.example .env  on Windows)
```

The `.env` file holds personal access tokens. It is git-ignored and must never
be committed. See `.env.example` for the variable names.

## Usage

Exact run commands, options and the day-to-day workflow are documented in
`CLAUDE.md`. Configuration defaults live in `config.yaml`. Output spreadsheets
are written locally and are git-ignored (they are data, not code).

## Tests

```bash
python -m pytest
```

## Notes

- Operational/run notes are kept local and are not part of this repository.
- Contributions are not being accepted; this is a personal project.
