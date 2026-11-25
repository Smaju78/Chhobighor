"""Shared helpers: catalogue loading, title normalising, slugs."""
import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"
DOCS = ROOT / "docs"


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s):
    """Lower-case ASCII words only: 'Mr. & Mrs. '55' -> 'mr mrs 55'."""
    s = strip_accents(s or "").lower().replace("&", " ").replace("'", "")
    return " ".join(re.findall(r"[a-z0-9]+", s))


def slug(s):
    return norm(s).replace(" ", "-")


def split(v):
    return [x.strip() for x in (v or "").split(";") if x.strip()]


def load_catalogue(include_generated=True):
    """Hand-picked films (catalogue.csv), then films found on the channels (catalogue_channels.csv, which carry
    their YouTube video id)."""
    films, seen = [], set()
    files = ["catalogue.csv"] + (["catalogue_channels.csv"] if include_generated else [])
    for name in files:
        if not (DATA / name).exists():
            continue
        with open(DATA / name, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                fid = f"{slug(r['title']) or slug(r.get('wikidata', ''))}-{r['year']}"
                if fid in seen:
                    continue
                seen.add(fid)
                films.append({
                    "id": fid, "section": r["section"], "title": r["title"], "alt": r["alt_title"] or "",
                    "year": int(r["year"]), "language": r["language"], "country": r["country"],
                    "directors": split(r["director"]), "genres": split(r.get("genres")), "cast": split(r["cast"]),
                    "video": r.get("video") or "",
                })
    return films


def titles(film):
    return [t for t in {norm(film["title"]), norm(film["alt"])} if t]


def contains_title(text, film):
    t = f" {norm(text)} "
    return any(f" {x} " in t for x in titles(film))


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
