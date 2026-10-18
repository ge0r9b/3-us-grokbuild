"""Serve the US districts map as a dynamic app.

File mode reads the static JavaScript already in this repo. When DATABASE_URL
is set and server/import_data.py has loaded that database, those rows are
served instead. GitHub Pages keeps serving the unchanged static v2/index.html.

    python3 server/app.py

The map is at http://127.0.0.1:8766/v2/
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import catalog

REPLACEMENTS = (
    (
        's.src = "../data/" + STATE_FILES[st] + "?v=" + window.BUILD;',
        's.src = datasetSrc("../data/" + STATE_FILES[st]);',
    ),
    (
        's.src = "../data/election2024.js?v=" + window.BUILD;',
        's.src = datasetSrc("../data/election2024.js");',
    ),
    (
        's.src = "../data/precincts2024/" + st.replace(/ /g, "_") + ".js?v=" + window.BUILD;',
        's.src = datasetSrc("../data/precincts2024/" + st.replace(/ /g, "_") + ".js");',
    ),
    (
        's.src="../data/election2020.js?v="+window.BUILD;',
        's.src=datasetSrc("../data/election2020.js");',
    ),
    (
        's.src="../data/zcta2024.js?v="+window.BUILD;',
        's.src=datasetSrc("../data/zcta2024.js");',
    ),
    (
        's.src="../data/precincts2020/"+st.replace(/ /g,"_")+".js?v="+window.BUILD;',
        's.src=datasetSrc("../data/precincts2020/"+st.replace(/ /g,"_")+".js");',
    ),
    (
        's.src="data/parts/"+STATE_FILES[st]+"?v="+window.BUILD;',
        's.src=datasetSrc("data/parts/"+STATE_FILES[st]);',
    ),
    (
        's.src="data/uscounties.js?v="+window.BUILD;',
        's.src=datasetSrc("data/uscounties.js");',
    ),
    (
        's.src="data/uscd.js?v="+window.BUILD;',
        's.src=datasetSrc("data/uscd.js");',
    ),
    (
        's.src="data/ak.js?v="+window.BUILD;',
        's.src=datasetSrc("data/ak.js");',
    ),
    (
        'sc.src="data/usstates.js?v="+window.BUILD;',
        'sc.src=datasetSrc("data/usstates.js");',
    ),
    (
        'ls.src="data/ctryshape.js?v="+window.BUILD;',
        'ls.src=datasetSrc("data/ctryshape.js");',
    ),
    (
        's.src="data/"+TFILE[k]+"?v="+window.BUILD;',
        's.src=datasetSrc("data/"+TFILE[k]);',
    ),
    (
        'cl.src="data/canada.js?v="+window.BUILD;',
        'cl.src=datasetSrc("data/canada.js");',
    ),
)

DATASET_FN = (
    "function datasetSrc(url){var path=String(url).replace(/\\?.*$/,\"\");"
    "return (window.API_BASE||\"\")+\"/api/dataset?path=\"+encodeURIComponent(path);}"
)


def rewrite_index(html, pack_literal, xref_literal):
    lines = html.split("\n")
    out = []
    injected = False
    for index, line in enumerate(lines):
        if line.startswith("const PACK = "):
            if out and out[-1].strip() == "<script>":
                out.pop()
            elif index == 0 or lines[index - 1].strip() != "<script>":
                raise ValueError("PACK assignment is not inside its own script tag")
            out.append("<script>window.__PACK = " + pack_literal + ";window.__XREF = " + xref_literal + ";</script>")
            out.append("<script>")
            out.append(DATASET_FN)
            out.append("const PACK = window.__PACK;")
            injected = True
            continue
        if line.startswith("const XREF = "):
            out.append("const XREF = window.__XREF;")
            continue
        if line.startswith("<script defer src=\"data/countries.js"):
            out.append('<script defer src="/api/dataset?path=data/countries.js"></script>')
            continue
        if line.startswith("<script src=\"data/dc.js"):
            out.append('<script src="/api/dataset?path=data/dc.js"></script>')
            continue
        for old, new in REPLACEMENTS:
            if old in line:
                line = line.replace(old, new, 1)
                break
        out.append(line)
    if not injected:
        raise ValueError("did not find the PACK assignment")
    rewritten = "\n".join(out)
    missing = [old for old, _new in REPLACEMENTS if old in rewritten]
    if missing:
        raise ValueError("static dataset URL still in the page: " + missing[0])
    return rewritten


def static_file(url_path):
    if url_path.startswith("/lib/"):
        root = (catalog.REPO / "lib").resolve()
        relative = url_path[len("/lib/"):]
    elif url_path.startswith("/v2/"):
        root = (catalog.REPO / "v2").resolve()
        relative = url_path[len("/v2/"):]
    else:
        return None
    if relative.endswith("/"):
        relative += "index.html"
    if relative == "" or ".." in Path_parts(relative):
        return None
    # Datasets are served by the API. Images, CSS, and Leaflet stay static.
    if url_path.startswith("/v2/data/") and relative.endswith(".js"):
        return None
    full = (root / relative).resolve()
    if full != root and root not in full.parents:
        return None
    if not full.is_file():
        return None
    return full


def Path_parts(relative):
    return relative.split("/")


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".md": "text/plain; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "us-districts-dynamic/1"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        self._respond()

    def do_HEAD(self):
        self._respond(head=True)

    def _respond(self, head=False):
        try:
            status, headers, body = route(self.path)
        except PermissionError:
            status, headers, body = 403, {"Content-Type": "text/plain; charset=utf-8"}, b"Forbidden"
        except FileNotFoundError:
            status, headers, body = 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not found"
        except Exception as exc:
            status, headers, body = 500, {"Content-Type": "text/plain; charset=utf-8"}, str(exc).encode("utf-8")
        if isinstance(body, str):
            body = body.encode("utf-8")
        headers = dict(headers)
        headers["Content-Length"] = str(len(body))
        headers.setdefault("Cache-Control", "no-cache")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)


def route(raw_path):
    parsed = urlparse(raw_path)
    path = unquote(parsed.path)
    query = parse_qs(parsed.query)
    if path == "/":
        return 302, {"Location": "/v2/", "Content-Type": "text/plain; charset=utf-8"}, b""
    if path == "/api/health":
        pack, source, error = catalog.read_body(catalog.PACK_PATH)
        payload = {
            "ok": True,
            "source": source,
            "database": bool(catalog.database_url()),
            "pack_bytes": len(pack),
        }
        if error:
            payload["database_error"] = error
        return 200, {"Content-Type": "application/json; charset=utf-8"}, json.dumps(payload)
    if path == "/api/pack":
        literal, source, _error = catalog.read_body(catalog.PACK_PATH)
        return json_response(catalog.parse_js_value(literal), source)
    if path == "/api/xref":
        literal, source, _error = catalog.read_body(catalog.XREF_PATH)
        return json_response(catalog.parse_js_value(literal), source)
    if path.startswith("/api/election/"):
        year = path[len("/api/election/"):]
        if year not in ("2020", "2024"):
            raise FileNotFoundError(year)
        text, source, _error = catalog.read_body("../data/election" + year + ".js")
        rows = catalog.election_rows(text, int(year))
        state = (query.get("state") or [None])[0]
        if state:
            rows = [row for row in rows if row[1] == state]
        payload = [
            {"state": row[1], "county": row[2], "dem": row[3], "rep": row[4], "total": row[5]}
            for row in rows
        ]
        return json_response(payload, source)
    if path == "/api/dataset":
        names = query.get("path") or []
        if len(names) != 1:
            raise PermissionError("path")
        text, source, _error = catalog.read_body(names[0])
        return 200, {
            "Content-Type": "text/javascript; charset=utf-8",
            "X-Data-Source": source,
        }, text
    if path in ("/v2", "/v2/", "/v2/index.html"):
        pack, _source, _error = catalog.read_body(catalog.PACK_PATH)
        xref, _xref_source, _error = catalog.read_body(catalog.XREF_PATH)
        html = rewrite_index(catalog.INDEX.read_text(encoding="utf-8"), pack, xref)
        return 200, {"Content-Type": "text/html; charset=utf-8"}, html
    found = static_file(path)
    if found is None:
        raise FileNotFoundError(path)
    kind = CONTENT_TYPES.get(found.suffix.lower(), "application/octet-stream")
    return 200, {"Content-Type": kind, "Cache-Control": "public, max-age=3600"}, found.read_bytes()


def json_response(payload, source):
    return 200, {
        "Content-Type": "application/json; charset=utf-8",
        "X-Data-Source": source,
    }, json.dumps(payload, separators=(",", ":"))


def main():
    host = os.environ.get("BIND", "127.0.0.1")
    port = int(os.environ.get("PORT", "8766"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("US districts dynamic app at http://%s:%s/v2/" % (host, port))
    httpd.serve_forever()


if __name__ == "__main__":
    main()
