"""Find each catalogue film on the Internet Archive, in its public-domain film collections only.

Writes cache/archive.json: {film_id: {identifier, title, downloads} | null}. Resumable; --redo to re-check all.
No API key needed.
"""
import argparse
import re
import time

import requests

from common import CACHE, load_catalogue, norm, read_json, titles, write_json

OUT = CACHE / "archive.json"
API = "https://archive.org/advancedsearch.php"
# Curated public-domain film collections. Random user uploads elsewhere are not used.
COLLECTIONS = ["feature_films", "silent_films", "SciFi_Horror", "Film_Noir", "comedy_films", "classic_cartoons",
               "Comedy_Films", "film_noir", "sci-fi_horror"]
BAD = re.compile(r"\b(trailer|clip|excerpt|scene|scenes|soundtrack|remake|colorized|colourized|preview|short|no audio|"
                 r"bdrip|bluray|blu ray|x264|x265|reup|webrip)\b", re.I)
# Words that may follow the film's title in an item title without making it a different film.
OK_TAIL = set("a the and film movie full silent complete restored version hd sd tinted subtitled english starring "
              "with director directed by in of b w bw color dvd quality mins min".split())


def tail_ok(film, rest):
    """'The Circus Queen Murder' is not 'The Circus': whatever follows the title must be a year, a credit or a descriptor."""
    names = " ".join(norm(n) for n in film["directors"] + film["cast"]).split()
    return all(w in OK_TAIL or w.isdigit() or w in names for w in rest.split())


def search(title):
    q = norm(title)
    coll = " OR ".join(COLLECTIONS)
    query = f'title:({q}) AND mediatype:movies AND (collection:({coll}) OR licenseurl:*publicdomain*)'
    params = [("q", query), ("rows", "40"), ("output", "json"), ("sort[]", "downloads desc")]
    params += [("fl[]", f) for f in ("identifier", "title", "year", "date", "downloads", "collection", "licenseurl")]
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, timeout=40, headers={"User-Agent": "chhobighor-catalogue/1.0"})
            r.raise_for_status()
            return r.json()["response"]["docs"]
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("archive.org search failed")


def year_of(doc):
    y = doc.get("year") or str(doc.get("date", ""))[:4]
    try:
        return int(str(y)[:4])
    except ValueError:
        return None


def first(v):
    return (v[0] if isinstance(v, list) else v) or ""


def pick(film, docs):
    """Item title must begin with the film's title; outside the curated collections the year must match too."""
    best, best_score = None, None
    for d in docs:
        t = first(d.get("title"))
        nt = norm(t)
        if BAD.search(t.replace(".", " ").replace("-", " ")) or BAD.search(d["identifier"].replace(".", " ").replace("-", " ")):
            continue
        heads = [x for x in titles(film) if nt == x or nt.startswith(x + " ")]
        if not heads:
            continue
        curated_tail = tail_ok(film, nt[len(max(heads, key=len)):])
        y = year_of(d)
        # A different year in the title or metadata usually means a remake or a different film.
        yt = [int(x) for x in re.findall(r"\b(18\d\d|19\d\d|20\d\d)\b", t)]
        if (y and 1895 < y < 2000 and abs(y - film["year"]) > 1) or any(abs(x - film["year"]) > 1 for x in yt):
            continue
        cols = d.get("collection") or []
        cols = [cols] if isinstance(cols, str) else cols
        curated = any(c in COLLECTIONS for c in cols)
        year_ok = any(abs(x - film["year"]) <= 1 for x in yt) or (y is not None and abs(y - film["year"]) <= 1)
        if not curated and not year_ok:
            continue
        if not curated_tail:
            continue
        score = (curated, year_ok, "ipod" not in d["identifier"].lower(), d.get("downloads") or 0)
        if best is None or score > best_score:
            best, best_score = d, score
    if not best:
        return None
    return {"identifier": best["identifier"], "title": first(best["title"]), "downloads": best.get("downloads") or 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--section", default="world", help="world (default), indian or all")
    a = ap.parse_args()
    cache = {} if a.redo else read_json(OUT, {})
    films = [f for f in load_catalogue() if a.section == "all" or f["section"] == a.section]
    for f in films:
        if f["id"] in cache:
            continue
        docs = search(f["title"])
        if f["alt"]:
            docs += search(f["alt"])
        cache[f["id"]] = pick(f, docs)
        print(f"{'found ' if cache[f['id']] else 'none  '} {f['title']} ({f['year']})"
              + (f"  -> {cache[f['id']]['identifier']} | {cache[f['id']]['title']}" if cache[f["id"]] else ""), flush=True)
        write_json(OUT, cache)
        time.sleep(0.5)
    found = sum(1 for f in films if cache.get(f["id"]))
    print(f"Archive: {found}/{len(films)} films found.")


if __name__ == "__main__":
    main()
