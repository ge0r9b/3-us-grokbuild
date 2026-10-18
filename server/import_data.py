"""Load the static datasets into the Postgres database from DATABASE_URL.

    python3 server/import_data.py

With --check, parse the files and print counts without connecting.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def counts():
    files = list(catalog.dataset_files())
    pack, xref = catalog.index_literals()
    pack_obj = catalog.parse_js_value(pack)
    xref_obj = catalog.parse_js_value(xref)
    elections = {}
    for year in (2020, 2024):
        text = (catalog.REPO / "data" / ("election%d.js" % year)).read_text(encoding="utf-8")
        elections[year] = len(catalog.election_rows(text, year))
    zcta = len(catalog.zcta_rows((catalog.REPO / "data" / "zcta2024.js").read_text(encoding="utf-8")))
    return {
        "files": len(files),
        "file_bytes": sum(path.stat().st_size for _key, path in files),
        "localities": len(pack_obj["lists"]["localities"]),
        "xref_ushouse": len(xref_obj["ushouse"]),
        "election_2020": elections[2020],
        "election_2024": elections[2024],
        "zcta": zcta,
    }


def import_all():
    if not catalog.database_url():
        raise SystemExit("DATABASE_URL is not set")
    summary = counts()
    with catalog.connect() as conn:
        with conn.cursor() as cur:
            for statement in SCHEMA.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cur.execute(statement)
            for key, file in catalog.dataset_files():
                body = file.read_text(encoding="utf-8")
                cur.execute(
                    """
                    INSERT INTO dataset (path, body, bytes)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (path) DO UPDATE
                    SET body = EXCLUDED.body, bytes = EXCLUDED.bytes, updated_at = now()
                    """,
                    (key, body, len(body.encode("utf-8"))),
                )
            pack, xref = catalog.index_literals()
            for key, body in ((catalog.PACK_PATH, pack), (catalog.XREF_PATH, xref)):
                cur.execute(
                    """
                    INSERT INTO dataset (path, body, bytes)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (path) DO UPDATE
                    SET body = EXCLUDED.body, bytes = EXCLUDED.bytes, updated_at = now()
                    """,
                    (key, body, len(body.encode("utf-8"))),
                )
            for year in (2020, 2024):
                text = (catalog.REPO / "data" / ("election%d.js" % year)).read_text(encoding="utf-8")
                for row in catalog.election_rows(text, year):
                    cur.execute(
                        """
                        INSERT INTO election_county (year, state, county, dem, rep, total)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (year, state, county) DO UPDATE
                        SET dem = EXCLUDED.dem, rep = EXCLUDED.rep, total = EXCLUDED.total
                        """,
                        row,
                    )
            for row in catalog.zcta_rows((catalog.REPO / "data" / "zcta2024.js").read_text(encoding="utf-8")):
                cur.execute(
                    """
                    INSERT INTO zcta (zip, lat, lon)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (zip) DO UPDATE
                    SET lat = EXCLUDED.lat, lon = EXCLUDED.lon
                    """,
                    row,
                )
        conn.commit()
    return summary


def main():
    if "--check" in sys.argv:
        for key, value in counts().items():
            print("%s %s" % (key, value))
        return
    summary = import_all()
    print("imported")
    for key, value in summary.items():
        print("%s %s" % (key, value))


if __name__ == "__main__":
    main()
