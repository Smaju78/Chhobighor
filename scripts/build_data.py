"""Merge the catalogue with the found sources into docs/films.json (only films that can be watched)."""
from datetime import date

from common import CACHE, DOCS, load_catalogue, read_json, write_json


def main():
    archive = read_json(CACHE / "archive.json", {})
    yt = read_json(CACHE / "youtube" / "matches.json", {})
    videos = read_json(CACHE / "youtube" / "videos.json", {})
    films, missing = [], []
    for f in load_catalogue():
        sources = []
        ids = [x for x in f["video"].split(";") if x]  # several ids: the film is on YouTube in parts, in order
        vs = [videos.get(x) for x in ids]
        if ids and all(vs):
            src = {"kind": "yt", "id": ids[0], "by": vs[0]["channel"], "mins": round(sum(v["secs"] for v in vs) / 60)}
            if len(ids) > 1:
                src["parts"] = ids
            sources.append(src)
        elif yt.get(f["id"]):
            m = yt[f["id"]]
            sources.append({"kind": "yt", "id": m["video"], "by": m["channel"], "mins": round(m["seconds"] / 60)})
        if archive.get(f["id"]):
            sources.append({"kind": "ia", "id": archive[f["id"]]["identifier"], "by": "Internet Archive"})
        if not sources:
            missing.append(f["title"])
            continue
        films.append({"id": f["id"], "s": f["section"], "t": f["title"], "a": f["alt"], "y": f["year"],
                      "l": f["language"], "c": f["country"], "d": f["directors"], "g": f["genres"], "cast": f["cast"], "src": sources})
    write_json(DOCS / "films.json", {"built": date.today().isoformat(), "films": films})
    print(f"docs/films.json: {len(films)} films ({sum(f['s'] == 'indian' for f in films)} Indian, "
          f"{sum(f['s'] == 'world' for f in films)} world). Not yet found: {len(missing)}.")


if __name__ == "__main__":
    main()
