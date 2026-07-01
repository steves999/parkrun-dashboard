#!/usr/bin/env python3
"""
Parkrun Dashboard Generator — Steve (ZL1SGS) · Athlete #2375160
Runs locally or via GitHub Actions (reads PARKRUN_COOKIE env var).
"""

import json, sys, re, os
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install requests beautifulsoup4 lxml")
    sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────
ATHLETE_ID   = "2375160"
ATHLETE_NAME = "Steve"
HOME_EVENT   = "pointchevalier"
CACHE_FILE   = Path("parkrun_cache.json")
OUTPUT_FILE  = Path("index.html")

EVENT_COUNTRY = {
    # NZ — add slugs as you visit new ones
    "pointchevalier":"NZ","cornwallpark":"NZ","owairaka":"NZ",
    "westernsprings":"NZ","northshore":"NZ","teatatu":"NZ",
    "lake2lake":"NZ","waitangi":"NZ","hagley":"NZ","newplymouth":"NZ",
    "mangere":"NZ","sherwoodreserve":"NZ","southernpath":"NZ",
    # UK
    "bushy":"UK","royalvictoriadock":"UK","southwark":"UK",
    "richmondpark":"UK","milton":"UK","parklands":"UK",
    # AU — ready for the 2027 trip
    "sydneyolympicpark":"AU","sydney":"AU","melbourne":"AU",
    "brisbane":"AU","perth":"AU","adelaide":"AU",
    "porthedland":"AU","cairns":"AU","darwin":"AU",
    "tennantscrk":"AU","alicesprings":"AU",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-NZ,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Referer": "https://www.parkrun.co.nz/",
}

# ── Scraper ──────────────────────────────────────────────────────────────────

def get_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(HEADERS)
    cookie_str = os.environ.get("PARKRUN_COOKIE", "")
    if cookie_str:
        # Set cookies on all parkrun domains
        for domain in [".parkrun.co.nz", ".parkrun.org.uk", ".parkrun.com.au"]:
            for part in cookie_str.split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, value = part.partition("=")
                    sess.cookies.set(name.strip(), value.strip(), domain=domain)
        print("✓ Session cookie loaded from environment")
    else:
        print("  No PARKRUN_COOKIE env var — attempting unauthenticated fetch")
    return sess


def fetch_results() -> list[dict]:
    sess = get_session()

    # Try the JSON results API first — more stable than HTML scraping
    runs = fetch_via_json_api(sess)
    if runs:
        return runs

    # Fallback: scrape the HTML results page
    print("  JSON API failed — trying HTML scrape...")
    urls = [
        f"https://www.parkrun.co.nz/parkrunner/{ATHLETE_ID}/all/",
        f"https://www.parkrun.org.uk/parkrunner/{ATHLETE_ID}/all/",
        f"https://www.parkrun.com.au/parkrunner/{ATHLETE_ID}/all/",
    ]
    for url in urls:
        try:
            r = sess.get(url, timeout=20)
            print(f"  {url} → {r.status_code}")
            if r.status_code == 200 and "results" in r.text.lower():
                runs = parse_page(r.text, url)
                if runs:
                    return runs
        except Exception as e:
            print(f"  Error: {e}")
    return []


def fetch_via_json_api(sess: requests.Session) -> list[dict]:
    """Parkrun exposes athlete results as JSON — faster and more reliable."""
    url = f"https://www.parkrun.org.uk/results/athleteresultshistory/?athleteNumber={ATHLETE_ID}&offset=0&numberofresults=1000"
    try:
        sess.headers.update({"Accept": "application/json, text/javascript, */*; q=0.01",
                              "X-Requested-With": "XMLHttpRequest"})
        r = sess.get(url, timeout=20)
        print(f"  JSON API → {r.status_code}")
        if r.status_code != 200:
            return []
        data = r.json()
        # Response structure: {"data": {"Results": [...]}}
        results = (data.get("data") or {}).get("Results", [])
        if not results:
            return []
        runs = []
        for res in results:
            try:
                event_raw  = res.get("EventLongName", res.get("EventName", "Unknown"))
                event_slug = re.sub(r"[^a-z0-9]", "", event_raw.lower())
                run_date   = res.get("RunDate", "")
                time_raw   = res.get("FinishTime", "0:00")
                pos        = str(res.get("AgeGrading", ""))
                ag         = float(str(res.get("AgeGrading", "0")).replace("%","").strip() or 0)

                parts = time_raw.strip().split(":")
                if len(parts) == 2:
                    secs = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    secs = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                else:
                    continue

                parsed_date = None
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
                    try:
                        parsed_date = datetime.strptime(run_date, fmt).date().isoformat()
                        break
                    except ValueError:
                        pass
                if not parsed_date:
                    continue

                country = EVENT_COUNTRY.get(event_slug, "NZ")

                runs.append({
                    "event": event_slug, "event_raw": event_raw,
                    "date": parsed_date, "run_no": str(res.get("EventNumber", "")),
                    "pos": str(res.get("Position", "")),
                    "secs": secs, "time": time_raw,
                    "age_grade": ag, "country": country,
                    "pb": bool(res.get("IsPersonalBest", False)),
                })
            except Exception:
                continue
        runs.sort(key=lambda r: r["date"])
        print(f"  JSON API: parsed {len(runs)} runs")
        return runs
    except Exception as e:
        print(f"  JSON API error: {e}")
        return []


def parse_page(html: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = (
        soup.find("table", id="results")
        or soup.find("table", class_=re.compile(r"results", re.I))
    )
    if not table:
        print("  No results table found in page")
        return []

    runs = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        try:
            event_raw  = cells[0].get_text(strip=True)
            event_slug = re.sub(r"[^a-z0-9]", "", event_raw.lower())
            run_date   = cells[1].get_text(strip=True)
            run_no     = cells[2].get_text(strip=True)
            pos        = cells[3].get_text(strip=True)
            time_raw   = cells[4].get_text(strip=True)
            age_grade  = cells[5].get_text(strip=True) if len(cells) > 5 else "0%"

            # Time → seconds
            parts = time_raw.strip().split(":")
            if len(parts) == 2:
                secs = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                secs = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
            else:
                continue

            # Date
            parsed_date = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
                try:
                    parsed_date = datetime.strptime(run_date, fmt).date().isoformat()
                    break
                except ValueError:
                    pass
            if not parsed_date:
                continue

            # Age grade
            try:
                ag = float(age_grade.replace("%","").strip())
            except ValueError:
                ag = 0.0

            # Country
            country = EVENT_COUNTRY.get(event_slug, "NZ" if "co.nz" in source_url else "OTHER")

            runs.append({
                "event": event_slug, "event_raw": event_raw,
                "date": parsed_date, "run_no": run_no, "pos": pos,
                "secs": secs, "time": time_raw,
                "age_grade": ag, "country": country,
                "pb": "PB" in row.get_text(),
            })
        except Exception:
            continue

    runs.sort(key=lambda r: r["date"])
    print(f"  Parsed {len(runs)} runs")
    return runs

# ── Stats ────────────────────────────────────────────────────────────────────

def fmt(secs):
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"

def compute_stats(runs):
    if not runs:
        return {}
    total = len(runs)
    pb_secs = min(r["secs"] for r in runs)
    pb_run  = next(r for r in runs if r["secs"] == pb_secs)

    by_year    = defaultdict(list)
    by_country = defaultdict(list)
    event_best = {}
    for r in runs:
        by_year[r["date"][:4]].append(r)
        by_country[r["country"]].append(r)
        if r["event"] not in event_best or r["secs"] < event_best[r["event"]]["secs"]:
            event_best[r["event"]] = r

    home_runs    = [r for r in runs if r["event"] == HOME_EVENT]
    tourist_runs = [r for r in runs if r["event"] != HOME_EVENT]
    best_ag      = max(runs, key=lambda r: r["age_grade"])

    milestones = {}
    for m in [25, 50, 100, 150, 200, 250, 500]:
        milestones[m] = runs[m-1] if len(runs) >= m else None

    first_letters = {r["event_raw"][0].upper() for r in runs if r["event_raw"]}
    alpha = {c: c in first_letters for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}

    counts = Counter(r["event"] for r in runs)
    seen, event_list = set(), []
    for r in runs:
        if r["event"] not in seen:
            event_list.append({
                "event": r["event_raw"],
                "slug":  r["event"],
                "country": r["country"],
                "count": counts[r["event"]],
            })
            seen.add(r["event"])

    return {
        "total":         total,
        "unique_events": len(event_best),
        "pb_time":       fmt(pb_secs),
        "pb_secs":       pb_secs,
        "pb_event":      pb_run["event_raw"],
        "pb_date":       pb_run["date"],
        "home_count":    len(home_runs),
        "tourist_count": len(tourist_runs),
        "tourist_pct":   round(100 * len(tourist_runs) / total) if total else 0,
        "by_country":    {k: len(v) for k, v in by_country.items()},
        "by_year":       {k: {"count": len(v), "best": fmt(min(r["secs"] for r in v))}
                          for k, v in by_year.items()},
        "milestones":    {str(k): v for k, v in milestones.items()},
        "best_ag":       best_ag,
        "best_ag_fmt":   f"{best_ag['age_grade']:.1f}%",
        "recent":        runs[-10:],
        "time_series":   [{"date": r["date"], "secs": r["secs"],
                           "event": r["event_raw"], "pb": r["pb"]} for r in runs],
        "alpha":         alpha,
        "event_list":    sorted(event_list, key=lambda e: e["country"]),
        "generated":     datetime.now().isoformat(),
    }

# ── HTML ─────────────────────────────────────────────────────────────────────

def generate_html(s, runs):
    gen = datetime.now().strftime("%d %b %Y %H:%M")
    total = s["total"]

    # Sparkline
    ts = s["time_series"]
    if len(ts) > 1:
        mn, mx = min(r["secs"] for r in ts), max(r["secs"] for r in ts)
        rng = mx - mn or 1
        W, H = 700, 90
        pts = " ".join(
            f"{i/(len(ts)-1)*W:.1f},{H-(r['secs']-mn)/rng*(H-12)-6:.1f}"
            for i, r in enumerate(ts)
        )
        # PB dots
        pb_dots = " ".join(
            f'<circle cx="{i/(len(ts)-1)*W:.1f}" cy="{H-(r["secs"]-mn)/rng*(H-12)-6:.1f}" r="3" fill="var(--green)"/>'
            for i, r in enumerate(ts) if r.get("pb")
        )
        sparkline = f'''<svg viewBox="0 0 {W} {H}" class="sparkline" xmlns="http://www.w3.org/2000/svg">
          <polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round"/>
          {pb_dots}
        </svg>
        <div class="chart-legend"><span class="dot-green"></span> PB &nbsp;·&nbsp; lower = faster</div>'''
    else:
        sparkline = "<p class='muted'>Not enough data yet</p>"

    # Country bars
    cc = s["by_country"]
    nz, uk, au = cc.get("NZ",0), cc.get("UK",0), cc.get("AU",0)
    mx_c = max(nz, uk, au, 1)

    def bar(flag, label, count, cls):
        w = round(count / mx_c * 100)
        return f'''<div class="bar-row">
          <span class="bar-flag">{flag}</span>
          <span class="bar-label">{label}</span>
          <div class="bar-track"><div class="bar-fill {cls}" style="width:{w}%"></div></div>
          <span class="bar-count">{count}</span>
        </div>'''

    country_bars = bar("🇳🇿","NZ",nz,"nz") + bar("🇬🇧","UK",uk,"uk") + bar("🇦🇺","AU",au,"au")

    # Event table (tourist)
    event_rows = "".join(
        f'<tr><td>{e["event"]}</td>'
        f'<td><span class="tag tag-{e["country"].lower()}">{e["country"]}</span></td>'
        f'<td class="mono">{e["count"]}</td></tr>'
        for e in s["event_list"]
    )

    # Recent
    recent_rows = "".join(
        f'<tr>'
        f'<td>{r["date"]}</td>'
        f'<td>{r["event_raw"]}</td>'
        f'<td class="mono{""}">{"🏅 " if r.get("pb") else ""}{r["time"]}</td>'
        f'<td class="mono">{r["age_grade"]:.1f}%</td>'
        f'</tr>'
        for r in reversed(s["recent"])
    )

    # Milestones
    def milestone_row(m):
        hit = s["milestones"].get(str(m))
        if hit:
            return f'<tr><td class="ms-num">{m}</td><td>{hit["event_raw"]}</td><td>{hit["date"]}</td></tr>'
        else:
            need = m - total
            return f'<tr class="dim"><td class="ms-num">{m}</td><td colspan="2">— {need} to go</td></tr>'

    ms_rows = "".join(milestone_row(m) for m in [25,50,100,150,200,250,500])

    # By year
    year_rows = "".join(
        f'<tr><td>{yr}</td><td>{d["count"]}</td><td class="mono">{d["best"]}</td></tr>'
        for yr in sorted(s["by_year"], reverse=True)
        for d in [s["by_year"][yr]]
    )

    # Alphabet
    alpha_cells = "".join(
        f'<span class="ac {"ac-done" if done else "ac-todo"}">{c}</span>'
        for c, done in s["alpha"].items()
    )
    done_count = sum(1 for v in s["alpha"].values() if v)
    missing = [c for c, v in s["alpha"].items() if not v]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Steve's Parkrun Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:      #0d1117;
  --surf:    #161b22;
  --surf2:   #21262d;
  --border:  #30363d;
  --text:    #e6edf3;
  --muted:   #7d8590;
  --accent:  #58a6ff;
  --green:   #3fb950;
  --orange:  #d29922;
  --purple:  #bc8cff;
  --red:     #f85149;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;
     font-size:14px;line-height:1.6;padding:1.5rem;max-width:1100px;margin:0 auto}}
a{{color:var(--accent);text-decoration:none}}
h2{{font-size:.75rem;font-weight:600;color:var(--muted);text-transform:uppercase;
    letter-spacing:.09em;margin-bottom:.9rem}}
.header{{display:flex;align-items:baseline;gap:1rem;margin-bottom:2rem;flex-wrap:wrap;
         border-bottom:1px solid var(--border);padding-bottom:1rem}}
.header h1{{font-size:1.5rem;font-weight:800;letter-spacing:-.02em}}
.gen{{font-size:.72rem;color:var(--muted)}}
/* Hero grid */
.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.75rem;margin-bottom:1.5rem}}
.stat{{background:var(--surf);border:1px solid var(--border);border-radius:8px;padding:1rem 1.2rem}}
.stat .val{{font-size:2rem;font-weight:800;line-height:1;letter-spacing:-.03em}}
.stat .val.c-accent{{color:var(--accent)}}
.stat .val.c-green {{color:var(--green)}}
.stat .val.c-orange{{color:var(--orange)}}
.stat .val.c-purple{{color:var(--purple)}}
.stat .lbl{{font-size:.72rem;color:var(--muted);margin-top:.25rem;text-transform:uppercase;letter-spacing:.05em}}
.stat .sub{{font-size:.75rem;color:var(--muted);margin-top:.3rem}}
/* Two-col layout */
.two{{display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-bottom:.75rem}}
@media(max-width:640px){{.two{{grid-template-columns:1fr}}}}
.panel{{background:var(--surf);border:1px solid var(--border);border-radius:8px;padding:1.2rem 1.4rem}}
.panel.wide{{margin-bottom:.75rem}}
/* Tables */
table{{width:100%;border-collapse:collapse;font-size:.83rem}}
th{{text-align:left;color:var(--muted);font-weight:500;padding:.35rem .5rem;
    border-bottom:1px solid var(--border)}}
td{{padding:.35rem .5rem;border-bottom:1px solid var(--border)}}
tr:last-child td{{border-bottom:none}}
.dim td{{color:var(--muted)}}
.ms-num{{font-family:'JetBrains Mono',monospace;font-weight:700;color:var(--orange)}}
.mono{{font-family:'JetBrains Mono',monospace}}
/* Chart */
.sparkline{{width:100%;height:90px;margin:.4rem 0}}
.chart-legend{{font-size:.72rem;color:var(--muted)}}
.dot-green{{display:inline-block;width:8px;height:8px;border-radius:50%;
            background:var(--green);vertical-align:middle}}
/* Country bars */
.bar-row{{display:flex;align-items:center;gap:.5rem;margin-bottom:.55rem;font-size:.83rem}}
.bar-flag{{font-size:1.1rem;line-height:1}}
.bar-label{{width:24px;color:var(--muted);font-size:.72rem}}
.bar-track{{flex:1;background:var(--surf2);border-radius:3px;height:8px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px;transition:width .4s}}
.bar-fill.nz{{background:var(--green)}}
.bar-fill.uk{{background:var(--accent)}}
.bar-fill.au{{background:var(--orange)}}
.bar-count{{width:28px;text-align:right;font-family:'JetBrains Mono',monospace;font-size:.8rem}}
/* Tags */
.tag{{display:inline-block;padding:.1rem .4rem;border-radius:4px;font-size:.7rem;font-weight:600}}
.tag-nz{{background:rgba(63,185,80,.2);color:var(--green)}}
.tag-uk{{background:rgba(88,166,255,.2);color:var(--accent)}}
.tag-au{{background:rgba(210,153,34,.2);color:var(--orange)}}
.tag-other{{background:var(--surf2);color:var(--muted)}}
/* Alphabet */
.alpha-grid{{display:flex;flex-wrap:wrap;gap:4px;margin:.5rem 0}}
.ac{{width:26px;height:26px;display:flex;align-items:center;justify-content:center;
     font-size:.75rem;font-weight:700;border-radius:4px}}
.ac-done{{background:var(--green);color:#0d1117}}
.ac-todo{{background:var(--surf2);color:var(--muted);border:1px solid var(--border)}}
.alpha-sub{{font-size:.75rem;color:var(--muted);margin-top:.4rem}}
.muted{{color:var(--muted);font-size:.83rem}}
.footer{{margin-top:1.5rem;font-size:.72rem;color:var(--muted);text-align:center;
         padding-top:1rem;border-top:1px solid var(--border)}}
</style>
</head>
<body>

<div class="header">
  <h1>🏃 Steve's Parkrun Dashboard</h1>
  <span class="gen">#{ATHLETE_ID} · updated {gen}</span>
</div>

<div class="hero">
  <div class="stat"><div class="val c-accent">{s['total']}</div><div class="lbl">Total parkruns</div></div>
  <div class="stat"><div class="val c-green">{s['pb_time']}</div><div class="lbl">Lifetime PB</div><div class="sub">{s['pb_event']} · {s['pb_date']}</div></div>
  <div class="stat"><div class="val c-orange">{s['unique_events']}</div><div class="lbl">Unique courses</div></div>
  <div class="stat"><div class="val c-purple">{s['best_ag_fmt']}</div><div class="lbl">Best age grade</div><div class="sub">{s['best_ag']['event_raw']} · {s['best_ag']['date']}</div></div>
  <div class="stat"><div class="val c-accent">{s['tourist_pct']}%</div><div class="lbl">Tourist runs</div><div class="sub">{s['tourist_count']} away · {s['home_count']} home</div></div>
</div>

<div class="two">
  <div class="panel">
    <h2>All times</h2>
    {sparkline}
  </div>
  <div class="panel">
    <h2>Recent runs</h2>
    <table>
      <tr><th>Date</th><th>Event</th><th>Time</th><th>AG%</th></tr>
      {recent_rows}
    </table>
  </div>
</div>

<div class="two">
  <div class="panel">
    <h2>Tourist map — NZ · UK · AU</h2>
    <div style="margin-bottom:1rem">{country_bars}</div>
    <table>
      <tr><th>Event</th><th></th><th>Visits</th></tr>
      {event_rows}
    </table>
  </div>
  <div class="panel">
    <h2>Milestones</h2>
    <table>
      <tr><th>#</th><th>Event</th><th>Date</th></tr>
      {ms_rows}
    </table>
    <div style="margin-top:1.2rem">
      <h2>By year</h2>
      <table>
        <tr><th>Year</th><th>Runs</th><th>Best</th></tr>
        {year_rows}
      </table>
    </div>
  </div>
</div>

<div class="panel wide">
  <h2>Alphabet challenge — {done_count}/26 done</h2>
  <div class="alpha-grid">{alpha_cells}</div>
  <div class="alpha-sub">Still needed: {', '.join(missing) if missing else '🎉 Complete!'}</div>
</div>

<div class="footer">
  Generated from parkrun.co.nz · athlete #{ATHLETE_ID} · {gen}
</div>
</body>
</html>"""

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Fetching results for athlete {ATHLETE_ID}...")
    runs = fetch_results()

    if runs:
        CACHE_FILE.write_text(json.dumps(runs, indent=2))
        print(f"✓ Cached {len(runs)} runs")
    elif CACHE_FILE.exists():
        runs = json.loads(CACHE_FILE.read_text())
        print(f"✓ Using cached data: {len(runs)} runs")
    else:
        print("No data available — see README for cookie setup")
        sys.exit(1)

    stats = compute_stats(runs)
    html  = generate_html(stats, runs)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"✓ Dashboard → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
