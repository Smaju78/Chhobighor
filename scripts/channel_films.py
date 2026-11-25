"""Add classic films that the allowed channels already host, with their details taken from Wikidata.

For every full-length, embeddable upload on the channels in data/channels.txt, the parts of the video title are
matched against the names of films in Wikidata (Indian, Soviet/Russian, Ukrainian, Hungarian, Polish, Georgian,
Persian languages). A film is kept only when:
  - Wikidata dates it to --max-year (default 1990) or earlier and it has at least --min-sitelinks Wikipedia
    articles (a measure of how notable it is),
  - the video's own title/description confirms it: the release year, the director or a lead actor is named.
Writes data/catalogue_channels.csv (generated: do not hand-edit; hand-picked films go in catalogue.csv).
Quota: about 1 unit per 50 uploads (cached per video). Wikidata needs no key.
"""
import argparse
import csv
import re
import time
import unicodedata

import requests

from common import CACHE, DATA, load_catalogue, read_json, write_json
from youtube_match import BAD, MIN_SECONDS, Api, QuotaExceeded, api_key, channels, crawl, iso_seconds, resolve

YT = CACHE / "youtube"
WD = CACHE / "wikidata"
SPARQL = "https://query.wikidata.org/sparql"
API = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "chhobighor-catalogue/1.0 (personal classic film list)"}
# Wikidata language item -> (label language code, display name, section)
LANGS = {
    "Q1568": ("hi", "Hindi", "indian"), "Q9610": ("bn", "Bengali", "indian"), "Q5885": ("ta", "Tamil", "indian"),
    "Q8097": ("te", "Telugu", "indian"), "Q36236": ("ml", "Malayalam", "indian"), "Q33673": ("kn", "Kannada", "indian"),
    "Q1571": ("mr", "Marathi", "indian"), "Q1617": ("ur", "Urdu", "indian"), "Q5137": ("gu", "Gujarati", "indian"),
    "Q58635": ("pa", "Punjabi", "indian"), "Q33810": ("or", "Odia", "indian"),
    "Q7737": ("ru", "Russian", "world"), "Q8798": ("uk", "Ukrainian", "world"), "Q9067": ("hu", "Hungarian", "world"),
    "Q809": ("pl", "Polish", "world"), "Q8108": ("ka", "Georgian", "world"), "Q9168": ("fa", "Persian", "world"),
}
NAME_LANGS = '"en","ru","uk","hu","pl","hi","bn"'
GENRES = [("noir", "Noir"), ("documentary", "Documentary"), ("animat", "Animation"), ("musical", "Musical"),
          ("comedy", "Comedy"), ("satir", "Satire"), ("romanc", "Romance"), ("romantic", "Romance"), ("horror", "Horror"),
          ("thriller", "Thriller"), ("crime", "Crime"), ("mystery", "Mystery"), ("detective", "Mystery"),
          ("war film", "War"), ("science fiction", "Sci-Fi"), ("fantasy", "Fantasy"), ("fairy", "Fantasy"),
          ("adventure", "Adventure"), ("action", "Action"), ("western", "Western"), ("historical", "Historical"),
          ("biographical", "Historical"), ("children", "Family"), ("family", "Family"), ("drama", "Drama")]
SPLIT = re.compile(r"\s*(?:\||｜|\(|\)|\[|\]|\{|\}|–|—|:| - |/|,|«|»|\")\s*")
NOISE = re.compile(r"\b(full movie|full film|full hd|fullhd|hd|4k|1080p|hindi movie|bengali movie|bengali full movie|"
                   r"hindi full movie|old hindi movie|classic|movie|film|with english subtitles|eng subs?|english subtitles|"
                   r"фильм|художественный фильм|teljes film)\b", re.I)


PARTS = re.compile(r"(\d\s*(серия|часть|rész|część)|(серия|часть|rész|część)\s*\d|\bpart\s*(\d|one|two|i\b|ii\b)|\bчасть\b)", re.I)
DISAMBIG = re.compile(r"\s*\((?:[^()]*\b(?:film|фильм|filmy?|телефильм|movie)\b[^()]*)\)\s*$", re.I)


def clean(label):
    """'Украденный поезд (фильм)' -> 'Украденный поезд'; 'Rakhi (1962 film)' -> 'Rakhi'."""
    return DISAMBIG.sub("", label or "").strip()

def key(s):
    """Script-neutral match key: lower case, Latin accents dropped, doubled Latin vowels folded (Awaara = Awara)."""
    s = unicodedata.normalize("NFC", s or "").casefold()
    s = "".join(unicodedata.normalize("NFKD", c)[0] if "a" <= unicodedata.normalize("NFKD", c)[0] <= "z" else c for c in s)
    s = " ".join(re.findall(r"\w+", s.replace("'", "").replace("&", " and ")))
    for a, b in (("aa", "a"), ("ee", "i"), ("oo", "u"), ("w", "v")):
        s = s.replace(a, b)
    return s


def sparql(query, tries=4):
    for i in range(tries):
        try:
            r = requests.post(SPARQL, data={"query": query, "format": "json"}, headers=UA, timeout=120)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(10 * (i + 1))
                continue
            raise RuntimeError(f"Wikidata HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException:
            time.sleep(10 * (i + 1))
    raise RuntimeError("Wikidata query failed")


def qid(b, k):
    return b[k]["value"].rsplit("/", 1)[-1]


def wikidata_films(max_year):
    """{qid: {year, sl, lang, labels{code: label}, keys{...}}} for films in the listed languages, cached per language."""
    films = {}
    for lq, (code, _, _) in LANGS.items():
        path = WD / f"films_{lq}.json"
        rows = read_json(path, None)
        if rows is None:
            print(f"  Wikidata: films in {LANGS[lq][1]}…", flush=True)
            rows = sparql(f"""SELECT ?film ?year ?sl ?label WHERE {{
              ?film wdt:P364 wd:{lq}; wdt:P31 wd:Q11424; wikibase:sitelinks ?sl; wdt:P577 ?d.
              BIND(YEAR(?d) AS ?year) FILTER(?year <= 1995)
              {{ ?film rdfs:label ?label }} UNION {{ ?film skos:altLabel ?label }}
              FILTER(LANG(?label) IN ("en", "{code}"))}}""")
            rows = [[qid(r, "film"), int(r["year"]["value"]), int(r["sl"]["value"]), r["label"]["value"],
                     r["label"].get("xml:lang", "")] for r in rows]
            write_json(path, rows)
            time.sleep(2)
        for q, y, sl, label, lg in rows:
            f = films.setdefault(q, {"year": y, "sl": sl, "lang": lq, "labels": {}, "keys": set()})
            f["year"] = min(f["year"], y)
            if lg not in f["labels"] or lg == "en" and len(label) < len(f["labels"]["en"]):
                f["labels"].setdefault(lg, label)
            f["keys"].add(key(label))
    return {q: f for q, f in films.items() if f["year"] <= max_year}


def entities(ids, props):
    """wbgetentities in batches of 50 (the Wikidata API, much faster than SPARQL for known items)."""
    out = {}
    for i in range(0, len(ids), 50):
        for attempt in range(4):
            try:
                r = requests.get(API, params={"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]), "props": props,
                                              "languages": NAME_LANGS.replace('"', "").replace(",", "|"), "format": "json"},
                                 headers=UA, timeout=60)
                if r.status_code == 200:
                    out.update(r.json().get("entities", {}))
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (attempt + 1))
        time.sleep(0.3)
    return out


def details(qids):
    """Directors, cast (billing order), genres, country for the given films, with names in several scripts. Cached."""
    path = WD / "details.json"
    cache = read_json(path, {})
    todo = [q for q in qids if q not in cache]
    if not todo:
        return cache
    print(f"  Wikidata details for {len(todo)} films…", flush=True)
    films = entities(todo, "claims")
    refs, wanted = {}, {"P57": "d", "P161": "c", "P136": "g", "P495": "k"}
    for q in todo:
        claims = films.get(q, {}).get("claims", {})
        refs[q] = {k: [c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get(p, [])
                       if c["mainsnak"].get("datavalue")] for p, k in wanted.items()}
    people = sorted({x for r in refs.values() for xs in r.values() for x in xs})
    ents = entities(people, "labels|sitelinks")
    for q in todo:
        cache[q] = {k: {x: {"sl": len(ents.get(x, {}).get("sitelinks", {}) or {}),
                            "names": {lg: v["value"] for lg, v in (ents.get(x, {}).get("labels", {}) or {}).items()}}
                        for x in xs} for k, xs in refs[q].items()}
    write_json(path, cache)
    return cache


def en(ent):
    n = ent["names"]
    return n.get("en") or next(iter(n.values()), "")


def video_info(api, ids):
    """Cached videos.list facts for full-length candidates."""
    path = YT / "videos.json"
    cache = read_json(path, {})
    todo = [v for v in ids if v not in cache]
    for i in range(0, len(todo), 50):
        res = api.get("videos", part="snippet,contentDetails,status,statistics", id=",".join(todo[i:i + 50]))
        got = {v["id"]: v for v in res.get("items", [])}
        for vid in todo[i:i + 50]:
            v = got.get(vid)
            if not v:
                cache[vid] = None
                continue
            reg = v["contentDetails"].get("regionRestriction", {})
            cache[vid] = {"secs": iso_seconds(v["contentDetails"].get("duration")),
                          "ok": v["status"].get("privacyStatus") == "public" and bool(v["status"].get("embeddable"))
                          and "IN" not in reg.get("blocked", []) and ("allowed" not in reg or "IN" in reg["allowed"]),
                          "title": v["snippet"]["title"], "text": (v["snippet"].get("description", "")[:1500] + " "
                                                                   + " ".join(v["snippet"].get("tags", []))),
                          "channel": v["snippet"]["channelTitle"], "views": int(v["statistics"].get("viewCount", 0))}
        if i % 2500 == 0:
            write_json(path, cache)
            print(f"  videos checked: {i + 50}/{len(todo)}", flush=True)
    write_json(path, cache)
    return cache


def confirmed(film, det, v):
    """The director or one of the first three billed actors must be named in full in the video's own text, and any
    year the video states must fit (same-title remakes are common: Rakhwala 1971 vs 1989)."""
    head = v["title"] + " " + v["text"][:300]
    years = [int(y) for y in re.findall(r"(?<!\d)(19[0-9]{2}|20[0-9]{2})(?!\d)", head)]
    if years and not any(abs(y - film["year"]) <= 1 for y in years):
        return False
    if re.search(r"\b(19[0-9]0|20[0-9]0)['’]?s\b", v["title"]):  # "90's Hits" etc. without a fitting year
        decade = int(re.search(r"(19[0-9]0|20[0-9]0)", v["title"]).group(1))
        if not decade <= film["year"] < decade + 10:
            return False
    if re.search(r"\b90['’]?s\b", v["title"]) and not 1990 <= film["year"] < 2000:
        return False
    text = f" {key(v['title'] + ' ' + v['text'])} "
    for p in list(det["d"].values()) + list(det["c"].values())[:3]:
        for n in p["names"].values():
            k = key(n)
            ws = k.split()
            # also first name + surname, since Russian labels carry a patronymic the uploads leave out
            for form in {k, f"{ws[0]} {ws[-1]}" if len(ws) > 2 else k}:
                if len(form) > 4 and " " in form and f" {form} " in text:
                    return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-year", type=int, default=1990)
    ap.add_argument("--min-sitelinks", type=int, default=3)
    ap.add_argument("--budget", type=int, default=9000)
    a = ap.parse_args()

    api = Api(api_key(), a.budget)
    uploads = {}
    try:
        for handle, label in channels():
            ch = resolve(api, handle)
            if ch:
                uploads.update(crawl(api, ch))
            else:
                print(f"  ! {handle} not found")
    except QuotaExceeded as e:
        print(f"Stopping: quota ({e}). Run again tomorrow.")
        return
    cands = [vid for vid, t in uploads.items() if not BAD.search(t) and not PARTS.search(t)]
    print(f"{len(uploads)} uploads, {len(cands)} possible films.", flush=True)
    try:
        info = video_info(api, cands)
    except QuotaExceeded as e:
        print(f"Stopping while checking videos: quota ({e}). Run again tomorrow to continue.")
        return

    films = wikidata_films(a.max_year)
    by_key = {}
    for q, f in films.items():
        if f["sl"] >= a.min_sitelinks:
            for k in f["keys"]:
                if len(k) > 2:
                    by_key.setdefault(k, []).append(q)
    pairs = []  # (video, qid)
    for vid in cands:
        v = info.get(vid)
        if not v or not v["ok"] or v["secs"] < MIN_SECONDS:
            continue
        for part in SPLIT.split(v["title"]):
            k = key(NOISE.sub(" ", part))
            for q in by_key.get(k, []):
                pairs.append((vid, q))
    det = details(sorted({q for _, q in pairs}))

    hand = {(key(f["title"]), f["year"]) for f in load_catalogue(include_generated=False)}
    hand |= {(key(f["alt"]), f["year"]) for f in load_catalogue(include_generated=False) if f["alt"]}
    best = {}
    for vid, q in pairs:
        f, d, v = films[q], det[q], info[vid]
        if not confirmed(f, d, v):
            continue
        latin = bool(re.search(r"[A-Za-z]{3}", v["title"]))  # prefer English-titled (subtitled) uploads
        score = (latin, v["views"])
        if q not in best or score > best[q][0]:
            best[q] = (score, vid)

    rows = []
    for q, (_, vid) in best.items():
        f, d = films[q], det[q]
        code, lang, section = LANGS[f["lang"]]
        title = clean(f["labels"].get("en") or f["labels"].get(code) or "")
        if not title or (key(title), f["year"]) in hand or (key(f["labels"].get(code, "")), f["year"]) in hand:
            continue
        alt = clean(f["labels"].get(code, "")) if key(clean(f["labels"].get(code, ""))) != key(title) else ""
        gl = " ".join(en(g).lower() for g in d["g"].values())
        genres = list(dict.fromkeys(name for word, name in GENRES if word in gl))[:3]
        countries = [en(c) for c in d["k"].values()]
        country = "India" if section == "indian" else (countries[0] if countries else "")
        cast = [en(c) for c in list(d["c"].values())[:5]]
        rows.append({"section": section, "title": title, "alt_title": alt, "year": f["year"], "language": lang,
                     "country": country, "director": ";".join(en(x) for x in d["d"].values()),
                     "genres": ";".join(genres), "cast": ";".join(cast), "video": vid, "wikidata": q})
    rows.sort(key=lambda r: (r["section"], r["language"], r["year"], r["title"]))
    with open(DATA / "catalogue_channels.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["section"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(f"data/catalogue_channels.csv: {len(rows)} films. " +
          ", ".join(f"{k}: {n}" for k, n in Counter(r["language"] for r in rows).most_common()))
    print(f"{api.quota['used']} YouTube units used today (PT).")


if __name__ == "__main__":
    main()
