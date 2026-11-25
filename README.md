# ছবিঘর · Chhobighor

Indian and world film classics that are free and legal to watch. A sister site to Anandadhara on the Sur hub.
Static site in `docs/` (GitHub Pages); a small Python pipeline finds where each film can be watched.

## Sources (and only these)
- **Rights holders' YouTube channels**, listed in `data/channels.txt` (Shemaroo, Ultra, Rajshri, NFDC, Angel…).
  Random uploads are never used.
- **Internet Archive** public-domain film collections (feature_films, silent_films, Film_Noir, …).

## Data
- `data/catalogue.csv`: the hand-curated list (section, title, alt title, year, language, country, directors, genres,
  cast; several values separated by `;`, main genre first). Add films here.
- `data/channels.txt`: allowed YouTube channels.

## Pipeline (run in WSL: `python3 scripts/...`)
1. `archive_match.py` finds world films on archive.org (no key; `--section all` to also try Indian films).
2. `youtube_match.py` reads the allowed channels' uploads and matches Indian films. Needs `YOUTUBE_API_KEY=...`
   in `.env` (gitignored). Uses about 1 quota unit per 50 uploads; stops at `--budget` and resumes next run.
3. `build_data.py` writes `docs/films.json` with every film that has at least one source.

Caches go in `cache/` (gitignored). Preview: serve `docs/` locally, e.g. `python3 -m http.server -d docs 8020`.
