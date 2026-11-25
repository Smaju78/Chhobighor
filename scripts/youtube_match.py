"""Find full films from the catalogue on the rights-holder channels in data/channels.txt.

Cheap on quota: it reads each channel's uploads list (1 unit per 50 videos) instead of searching
(100 units per search), matches titles locally, then checks candidates with videos.list (1 unit per 50):
full length (>= 70 min), embeddable, public, and the description names the director or a lead actor.

Needs YOUTUBE_API_KEY in .env. Quota is tracked per Pacific-time day in cache/youtube/_quota.json and the
run stops before --budget (default 9000). Resumable: uploads lists are cached per channel and refreshed
only from the newest end.
"""
import argparse
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from common import CACHE, DATA, ROOT, load_catalogue, norm, read_json, strip_accents, titles, write_json

API = "https://www.googleapis.com/youtube/v3"
OUT = CACHE / "youtube"
QUOTA_FILE = OUT / "_quota.json"
BAD = re.compile(r"\b(trailer|teaser|song|songs|scene|scenes|jukebox|dialogue|dialogues|climax|best of|"
                 r"part \d|promo|making|review|explained|spoof|title track|audio|lyrical|shorts)\b", re.I)
MIN_SECONDS = 70 * 60


class QuotaExceeded(Exception):
    pass


def api_key():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "YOUTUBE_API_KEY":
                return v.strip().strip('"').strip("'")
    sys.exit("YOUTUBE_API_KEY not found in .env (create .env with YOUTUBE_API_KEY=...)")


def pt_today():
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


class Api:
    def __init__(self, key, budget):
        self.key, self.budget = key, budget
        q = read_json(QUOTA_FILE, {})
        self.quota = q if q.get("date") == pt_today() else {"date": pt_today(), "used": 0}

    def get(self, endpoint, **params):
        if self.quota["used"] + 1 > self.budget:
            raise QuotaExceeded("budget")
        params["key"] = self.key
        try:
            r = requests.get(f"{API}/{endpoint}", params=params, timeout=30)
        except requests.RequestException as e:  # never print the URL: it holds the key
            raise RuntimeError(f"{endpoint}: network error {type(e).__name__}") from None
        self.quota["used"] += 1
        write_json(QUOTA_FILE, self.quota)
        if r.status_code == 200:
            return r.json()
        try:
            reason = r.json()["error"]["errors"][0].get("reason", "")
        except Exception:
            reason = ""
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise QuotaExceeded(reason)
        raise RuntimeError(f"{endpoint}: HTTP {r.status_code} {reason}")


def channels():
    out = []
    for line in (DATA / "channels.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            handle, _, label = line.partition(" ")
            out.append((handle, label.strip() or handle))
    return out


def resolve(api, handle):
    known = read_json(OUT / "_channels.json", {})
    if handle not in known:
        items = api.get("channels", part="snippet,contentDetails", forHandle=handle).get("items", [])
        known[handle] = None if not items else {
            "id": items[0]["id"], "title": items[0]["snippet"]["title"],
            "uploads": items[0]["contentDetails"]["relatedPlaylists"]["uploads"]}
        write_json(OUT / "_channels.json", known)
    return known[handle]


def crawl(api, ch):
    """Uploads as {videoId: title}; resumes a partial crawl and tops up a complete one from the newest end."""
    path = OUT / f"uploads_{ch['id']}.json"
    data = read_json(path, {"videos": {}, "complete": False, "next": None})
    vids, token = data["videos"], (None if data["complete"] else data["next"])
    topping_up = data["complete"]
    while True:
        res = api.get("playlistItems", part="snippet", playlistId=ch["uploads"], maxResults=50,
                      **({"pageToken": token} if token else {}))
        new = 0
        for it in res.get("items", []):
            vid = it["snippet"]["resourceId"]["videoId"]
            if vid not in vids:
                vids[vid] = it["snippet"]["title"]
                new += 1
        token = res.get("nextPageToken")
        data.update(videos=vids, next=token)
        if not token:
            data["complete"] = True
        write_json(path, data)
        if not token or (topping_up and new == 0):
            break
        if len(vids) % 2500 < 50:
            print(f"    {ch['title']}: {len(vids)} uploads read", flush=True)
    return vids


TAG = r"(?:\s*$|\s*[-|({\[:,–]|\s+(?:full|hd|19\d\d|movie|film|hindi|bengali|old|classic)\b)"


def leads_with(video_title, film):
    """These channels name full films 'Title (HD) - cast | ...': the film's title must open the video title and be
    followed by a separator, a year or a tag, so 'Awara Paagal Deewana' is not 'Awaara'."""
    t = strip_accents(video_title).lower().replace("'", "")
    for x in titles(film):
        words = [r"(?:and|&)" if w == "and" else re.escape(w) for w in x.split()]
        if re.match(r"^\W*" + r"\W+".join(words) + TAG, t):
            return True
    return False


def iso_seconds(d):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 86400 + h * 3600 + mi * 60 + s


def surname(name):
    return norm(name).split()[-1] if norm(name) else ""


def credible(film, v):
    """The video's own text must name a director or a lead actor (guards against remakes and namesakes)."""
    text = f" {norm(v['snippet']['title'] + ' ' + v['snippet'].get('description', '') + ' ' + ' '.join(v['snippet'].get('tags', [])))} "
    names = film["directors"] + film["cast"][:3]
    if any(f" {norm(n)} " in text for n in names):
        return True
    return sum(1 for n in names if len(surname(n)) > 3 and f" {surname(n)} " in text) >= 2


def check(api, films_by_vid):
    """videos.list on candidate ids; returns {film_id: best video dict}."""
    ids, best = list(films_by_vid), {}
    for i in range(0, len(ids), 50):
        res = api.get("videos", part="snippet,contentDetails,status,statistics", id=",".join(ids[i:i + 50]))
        for v in res.get("items", []):
            st = v["status"]
            if st.get("privacyStatus") != "public" or not st.get("embeddable"):
                continue
            secs = iso_seconds(v["contentDetails"].get("duration"))
            if secs < MIN_SECONDS:
                continue
            region = v["contentDetails"].get("regionRestriction", {})
            if "IN" in region.get("blocked", []) or ("allowed" in region and "IN" not in region["allowed"]):
                continue
            for film in films_by_vid[v["id"]]:
                yrs = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", v["snippet"]["title"])]
                if any(abs(y - film["year"]) > 1 for y in yrs) or not credible(film, v):
                    continue
                views = int(v["statistics"].get("viewCount", 0))
                cur = best.get(film["id"])
                if not cur or views > cur["views"]:
                    best[film["id"]] = {"video": v["id"], "title": v["snippet"]["title"],
                                        "channel": v["snippet"]["channelTitle"], "channelId": v["snippet"]["channelId"],
                                        "seconds": secs, "views": views}
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=9000)
    ap.add_argument("--section", default="indian", help="indian (default), world or all")
    a = ap.parse_args()
    api = Api(api_key(), a.budget)
    films = [f for f in load_catalogue() if a.section == "all" or f["section"] == a.section]
    uploads = {}
    try:
        for handle, label in channels():
            ch = resolve(api, handle)
            if not ch:
                print(f"  ! {handle} ({label}) not found: check the handle")
                continue
            print(f"  {handle} -> {ch['title']}", flush=True)
            for vid, t in crawl(api, ch).items():
                uploads[vid] = t
    except QuotaExceeded as e:
        print(f"Stopping: quota ({e}). {api.quota['used']} units used today (PT). Run again tomorrow to resume.")
    cands = {}
    for vid, t in uploads.items():
        if BAD.search(t):
            continue
        for f in films:
            if leads_with(t, f):
                cands.setdefault(vid, []).append(f)
    print(f"{len(uploads)} uploads read, {len(cands)} title candidates.", flush=True)
    try:
        best = check(api, cands)
    except QuotaExceeded as e:
        print(f"Stopping before checking candidates: quota ({e}).")
        return
    prev = best  # rebuilt every run, so a tightened rule or a removed video drops a stale match
    write_json(OUT / "matches.json", prev)
    print(f"YouTube: {sum(1 for f in films if f['id'] in prev)}/{len(films)} films matched. "
          f"{api.quota['used']} units used today (PT).")
    for f in films:
        if f["id"] not in prev:
            print(f"  none  {f['title']} ({f['year']})")


if __name__ == "__main__":
    main()
