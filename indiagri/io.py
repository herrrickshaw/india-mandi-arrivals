"""Small stdlib helpers shared by the collectors: gzipped CSV output and a JSON response cache."""
import csv
import gzip
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / ".cache"          # raw API responses, gitignored; makes every collector resumable

# Fields never written to the repo: market profiles carry officials' names and phone numbers.
PRIVATE_FIELDS = {"phone", "mobile", "email", "contact", "contact_person", "officer", "fax", "telephone"}


def _flat(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return v


def write_rows(path, rows, fields=None):
    """Write dict rows to a .csv.gz (columns = union of keys in first-seen order). Returns row count."""
    path = DATA / path
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if fields is None:
        fields, seen = [], set()
        for r in rows:
            for k in r:
                if k not in seen and not any(p in k.lower() for p in PRIVATE_FIELDS):
                    seen.add(k); fields.append(k)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _flat(r.get(k)) for k in fields})
    return len(rows)


def read_rows(path):
    with gzip.open(DATA / path, "rt", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def cached(name, fn):
    """Return fn() result, caching JSON under .cache/<name>.json so reruns skip finished calls."""
    CACHE.mkdir(exist_ok=True)
    safe = name if len(name) < 120 else hashlib.sha1(name.encode()).hexdigest()
    f = CACHE / f"{safe}.json"
    if f.exists():
        return json.loads(f.read_text())
    out = fn()
    f.write_text(json.dumps(out, ensure_ascii=False))
    return out
