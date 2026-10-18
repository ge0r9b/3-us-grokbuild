"""Read the static US districts files and the optional Postgres copy of them."""

import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "v2" / "index.html"

PACK_PATH = "__pack__"
XREF_PATH = "__xref__"

_BARE_KEY = re.compile(r"([\{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")


def database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    return url or None


def quote_bare_keys(src):
    return _BARE_KEY.sub(r'\1"\2":', src)


def parse_js_value(src):
    """Parse a JavaScript object or array that is JSON aside from bare keys."""
    value = quote_bare_keys(src.strip())
    return json.loads(value)


def literal_from_assignment(line, name):
    prefix = "const " + name + " = "
    if not line.startswith(prefix) or not line.rstrip().endswith(";"):
        raise ValueError("index.html has no single-line " + name + " assignment")
    return line.strip()[len(prefix):-1]


def index_literals(text=None):
    text = INDEX.read_text(encoding="utf-8") if text is None else text
    pack = xref = None
    for line in text.split("\n"):
        if line.startswith("const PACK = "):
            pack = literal_from_assignment(line, "PACK")
        elif line.startswith("const XREF = "):
            xref = literal_from_assignment(line, "XREF")
    if not pack or not xref:
        raise ValueError("PACK or XREF is missing from v2/index.html")
    return pack, xref


def resolve_dataset(path):
    """Map a page path to a file under data/ or v2/data/. Reject escapes."""
    path = path.split("?", 1)[0]
    if path.startswith("../data/"):
        relative = path[len("../data/"):]
        root = (REPO / "data").resolve()
    elif path.startswith("data/"):
        relative = path[len("data/"):]
        root = (REPO / "v2" / "data").resolve()
    else:
        raise PermissionError(path)
    if relative == "" or relative.startswith("/") or "\\" in relative:
        raise PermissionError(path)
    parts = Path(relative).parts
    if ".." in parts:
        raise PermissionError(path)
    full = (root / relative).resolve()
    if full != root and root not in full.parents:
        raise PermissionError(path)
    return full


def read_file(path):
    return resolve_dataset(path).read_text(encoding="utf-8")


def connect():
    import psycopg
    return psycopg.connect(database_url(), connect_timeout=3)


def body_from_database(path):
    url = database_url()
    if not url:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT body FROM dataset WHERE path = %s", (path,))
            row = cur.fetchone()
    return row[0] if row else None


def read_body(path):
    """Return (text, source). Database wins when that path has been imported."""
    if database_url():
        try:
            stored = body_from_database(path)
        except Exception as exc:
            return read_file(path) if path not in (PACK_PATH, XREF_PATH) else _literal(path), "file", str(exc)
        if stored is not None:
            return stored, "database", None
    if path in (PACK_PATH, XREF_PATH):
        return _literal(path), "file", None
    return read_file(path), "file", None


def _literal(path):
    pack, xref = index_literals()
    return pack if path == PACK_PATH else xref


def object_from_script(text):
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("script has no object")
    return json.loads(text[start:end + 1])


def election_rows(text, year):
    data = object_from_script(text)
    rows = []
    for key, value in data.items():
        state, county = key.split("|", 1)
        dem, rep, total = value
        rows.append((year, state, county, int(dem), int(rep), int(total)))
    return rows


def zcta_rows(text):
    data = object_from_script(text)
    return [(zip_code, float(lat), float(lon)) for zip_code, (lat, lon) in data.items()]


def dataset_files():
    """Yield (api path, file) for every JavaScript dataset."""
    roots = ((REPO / "data", "../data/"), (REPO / "v2" / "data", "data/"))
    for root, prefix in roots:
        for file in sorted(root.rglob("*.js")):
            relative = file.relative_to(root).as_posix()
            yield prefix + relative, file
