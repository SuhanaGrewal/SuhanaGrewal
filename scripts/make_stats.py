#!/usr/bin/env python3
"""Live GitHub stats strip, blueprint aesthetic (white paper / blue ink).

Fetches real numbers from the GitHub API and renders an SVG. Designed to be run
on a schedule by GitHub Actions, which commits the refreshed SVG back to the repo.

    python3 make_stats.py                  # one wide row  -> stats.svg
    python3 make_stats.py --tiles          # 4 square tiles -> stats-1.svg ...

Auth: reads GITHUB_TOKEN from the environment; falls back to `gh auth token`
locally. The contributions/streak figures require GraphQL, which needs a token.
"""
import json
import math
import os
import subprocess
import sys
import urllib.request
import datetime

USER = os.environ.get("GH_USER", "SuhanaGrewal")
OUTDIR = os.environ.get("STATS_OUTDIR", os.path.dirname(os.path.abspath(__file__)))

# Which four stats to show, in order. Available keys:
#   stars, repos, contributions, forks, followers, streak, longest_streak, active_days
STATS = ("stars", "repos", "contributions", "streak")

# ------------------------------------------------------------------ palette
# Ink matches the mid stop of the header.svg background gradient, so the text
# here is literally the same blue as that banner's paper.
INK = "#134a91"      # primary blue - numbers, icons
INK2 = "#1a5cad"
MUTED = "#2f5fa8"    # labels
FAINT = "#5c85bd"    # borders, stamp
GRID = "#3f6aa8"
SERIF = ("'Hoefler Text', Baskerville, 'Palatino Linotype', Palatino, "
         "'Book Antiqua', Georgia, 'Times New Roman', serif")
MONO = "ui-monospace, 'JetBrains Mono', 'Courier New', monospace"
SF = ("-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', "
      "Helvetica, Arial, sans-serif")


# ------------------------------------------------------------------- fetch
def token():
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if t:
        return t.strip()
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def api(url, tok):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "blueprint-stats",
        **({"Authorization": f"Bearer {tok}"} if tok else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def graphql(query, variables, tok):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "User-Agent": "blueprint-stats",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


def collect():
    tok = token()
    data = {}

    # --- REST: repos, stars, forks, followers -------------------------
    stars = forks = repos = 0
    page = 1
    while True:
        batch = api(f"https://api.github.com/users/{USER}/repos"
                    f"?per_page=100&type=owner&page={page}", tok)
        if not batch:
            break
        for r in batch:
            if r.get("fork"):
                continue
            repos += 1
            stars += r.get("stargazers_count", 0)
            forks += r.get("forks_count", 0)
        if len(batch) < 100:
            break
        page += 1
    profile = api(f"https://api.github.com/users/{USER}", tok)
    data.update(stars=stars, forks=forks, repos=repos,
                followers=profile.get("followers", 0))

    # --- GraphQL: contribution calendar -------------------------------
    data.update(contributions=0, streak=0, longest_streak=0, active_days=0)
    if not tok:
        print("warning: no token, skipping contributions/streak", file=sys.stderr)
        return data
    try:
        q = """query($u:String!){user(login:$u){contributionsCollection{
                 contributionCalendar{ totalContributions
                   weeks{ contributionDays{ date contributionCount } } } } } }"""
        cal = graphql(q, {"u": USER}, tok)["user"]["contributionsCollection"]["contributionCalendar"]
        data["contributions"] = cal["totalContributions"]
        days = sorted((d for w in cal["weeks"] for d in w["contributionDays"]),
                      key=lambda d: d["date"])
        today = datetime.date.today()
        days = [d for d in days if datetime.date.fromisoformat(d["date"]) <= today]
        # current streak: walk back from today; today being empty doesn't break it
        cur = 0
        for i, d in enumerate(reversed(days)):
            if d["contributionCount"] > 0:
                cur += 1
            elif i == 0:
                continue          # today not counted yet
            else:
                break
        best = run = 0
        for d in days:
            run = run + 1 if d["contributionCount"] > 0 else 0
            best = max(best, run)
        data.update(streak=cur, longest_streak=best,
                    active_days=sum(1 for d in days if d["contributionCount"] > 0))
    except Exception as e:
        print(f"warning: contributions unavailable ({e})", file=sys.stderr)
    return data


# -------------------------------------------------------------------- icons
def pol(cx, cy, r, a):
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def path_star(r=9):
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.42
        pts.append(pol(0, 0, rad, -math.pi / 2 + i * math.pi / 5))
    d = "M %.2f %.2f " % pts[0] + " ".join("L %.2f %.2f" % p for p in pts[1:]) + " Z"
    return f'<path d="{d}" stroke-width="1.15"/>'


def path_repo(w=19, h=15):
    x, y = -w / 2, -h / 2
    return (f'<path d="M {x:.1f} {y+3:.1f} h 7 v -3 h {w-7:.1f} v {h:.1f} h -{w:.1f} Z" '
            f'stroke-width="1.2"/>'
            f'<path d="M {x:.1f} {y+3:.1f} h {w:.1f}" stroke-width="0.75"/>')


def path_pulse(w=24, h=14):
    x = -w / 2
    return (f'<path d="M {x:.1f} 0 h {w*0.2:.1f} l {w*0.13:.1f} {-h:.1f} '
            f'l {w*0.16:.1f} {h*1.55:.1f} l {w*0.13:.1f} {-h*0.8:.1f} h {w*0.38:.1f}" '
            'stroke-width="1.25"/>')


def path_fork():
    return ('<circle cx="-7" cy="-7" r="3.4" stroke-width="1.15"/>'
            '<circle cx="7" cy="-7" r="3.4" stroke-width="1.15"/>'
            '<circle cx="0" cy="8" r="3.4" stroke-width="1.15"/>'
            '<path d="M -7 -3.6 v 3 a 4 4 0 0 0 4 4 h 6 a 4 4 0 0 0 4 -4 v -3" '
            'stroke-width="1.1"/><path d="M 0 4.6 V 3.4" stroke-width="1.1"/>')


def path_users(r=6.6):
    return (f'<circle cx="-4.4" cy="0" r="{r}" stroke-width="1.15"/>'
            f'<circle cx="4.4" cy="0" r="{r}" stroke-width="1.15"/>')


def path_flame():
    """Fire: outer flame with a lick on the left, plus an inner core."""
    outer = ("M 0 -14 "
             "C -2 -8.5, -4.6 -6.6, -5.8 -3.4 "
             "C -6.4 -5.2, -6.5 -7, -6.1 -8.6 "
             "C -8.8 -5.2, -9.6 -0.6, -8.5 3 "
             "C -7.2 7.6, -3.8 11, 0 11 "
             "C 4.2 11, 7.9 7.4, 8.2 2.8 "
             "C 8.5 -2.4, 5.2 -6.2, 2.4 -9 "
             "C 1.3 -10.1, 0.4 -12.2, 0 -14 Z")
    inner = ("M 0 -2.4 "
             "C -1.4 0.2, -3.4 1.8, -3.4 4.5 "
             "C -3.4 7.4, -1.6 9.2, 0 9.2 "
             "C 1.7 9.2, 3.6 7.4, 3.6 4.5 "
             "C 3.6 1.8, 1.4 0.2, 0 -2.4 Z")
    return (f'<path d="{outer}" stroke-width="1.2"/>'
            f'<path d="{inner}" stroke-width="0.9" stroke-opacity="0.8"/>')


SPECS = {
    "stars":          (path_star,  "Total Stars", None),
    "repos":          (path_repo,  "Repositories", None),
    "contributions":  (path_pulse, "Contributions", "(this year)"),
    "forks":          (path_fork,  "Total Forks", None),
    "followers":      (path_users, "Followers", None),
    "streak":         (path_flame, "Current Streak", "(days)"),
    "longest_streak": (path_flame, "Longest Streak", "(days)"),
    "active_days":    (path_pulse, "Active Days", "(this year)"),
}


# ------------------------------------------------------------------- render
def defs(W, H):
    return f'''<defs>
 <linearGradient id="bg" x1="0" y1="0" x2="0.4" y2="1">
  <stop offset="0" stop-color="#d8e6f7"/><stop offset="0.55" stop-color="#c8dcf2"/>
  <stop offset="1" stop-color="#b7cdea"/></linearGradient>
 <pattern id="g1" width="10" height="10" patternUnits="userSpaceOnUse">
  <path d="M10 0H0V10" fill="none" stroke="{GRID}" stroke-opacity="0.13" stroke-width="0.5"/></pattern>
 <pattern id="g2" width="50" height="50" patternUnits="userSpaceOnUse">
  <path d="M50 0H0V50" fill="none" stroke="{GRID}" stroke-opacity="0.2" stroke-width="0.7"/></pattern>
 <filter id="hand" x="-8%" y="-8%" width="116%" height="116%">
  <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="3" seed="11" result="n"/>
  <feDisplacementMap in="SourceGraphic" in2="n" scale="1.0" xChannelSelector="R" yChannelSelector="G"/>
 </filter>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<rect width="{W}" height="{H}" fill="url(#g1)"/>
<rect width="{W}" height="{H}" fill="url(#g2)"/>'''


def cell(icon_fn, value, label, sub, ix, iy, nx, ny):
    """icon at (ix,iy); number/label block starting at nx"""
    o = [f'<g filter="url(#hand)" fill="none" stroke="{INK}" stroke-linecap="round" '
         f'stroke-linejoin="round" transform="translate({ix:.1f},{iy:.1f})">{icon_fn()}</g>']
    o.append(f'<text x="{nx:.1f}" y="{ny:.1f}" font-family="{MONO}" font-size="34" '
             f'font-weight="600" fill="{INK}" letter-spacing="-0.5">{value}</text>')
    o.append(f'<text x="{nx:.1f}" y="{ny+24:.1f}" font-family="{SF}" font-size="13" '
             f'font-weight="500" fill="{MUTED}">{label}</text>')
    if sub:
        o.append(f'<text x="{nx:.1f}" y="{ny+40:.1f}" font-family="{SF}" font-size="11" '
                 f'fill="{FAINT}" fill-opacity="0.9">{sub}</text>')
    return "".join(o)


def stamp(W, H, when, pad_x=18, pad_y=12):
    return (f'<text x="{W-pad_x}" y="{H-pad_y}" font-family="{MONO}" font-size="8.5" '
            f'text-anchor="end" fill="{FAINT}" fill-opacity="0.55" '
            f'letter-spacing="1">UPD {when}</text>')


def render_row(data, when):
    """Four discrete boxes on one row - separate cards, but a single SVG so
    they can never wrap or drift out of alignment in a README."""
    W, H = 1200, 230
    M, GAP = 34, 20
    bw = (W - 2 * M - 3 * GAP) / 4
    by, bh = 28, 164
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}">', defs(W, H)]
    for i, key in enumerate(STATS):
        icon_fn, label, sub = SPECS[key]
        x = M + i * (bw + GAP)
        cx = x + bw / 2
        o.append(f'<rect x="{x:.1f}" y="{by}" width="{bw:.1f}" height="{bh}" rx="12" '
                 f'fill="none" stroke="{FAINT}" stroke-width="1" stroke-opacity="0.65"/>')
        o.append(f'<g filter="url(#hand)" fill="none" stroke="{INK}" stroke-linecap="round" '
                 f'stroke-linejoin="round" transform="translate({cx:.1f},{by+44}) scale(1.6)">'
                 f'{icon_fn()}</g>')
        o.append(f'<text x="{cx:.1f}" y="{by+108}" font-family="{MONO}" font-size="46" '
                 f'font-weight="600" text-anchor="middle" fill="{INK}" '
                 f'letter-spacing="-1">{data.get(key,0):,}</text>')
        o.append(f'<text x="{cx:.1f}" y="{by+134}" font-family="{SF}" font-size="14.5" '
                 f'font-weight="500" text-anchor="middle" fill="{MUTED}">{label}</text>')
        if sub:
            o.append(f'<text x="{cx:.1f}" y="{by+152}" font-family="{SF}" font-size="11.5" '
                     f'text-anchor="middle" fill="{FAINT}">{sub}</text>')
    o.append(stamp(W, H, when))
    o.append("</svg>")
    return "\n".join(o)


def render_tile(key, data, when):
    """One stat, square, for dropping into a 4-column README table."""
    W, H = 300, 230
    icon_fn, label, sub = SPECS[key]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}">', defs(W, H)]
    o.append(f'<rect x="10" y="10" width="{W-20}" height="{H-20}" rx="14" fill="none" '
             f'stroke="{FAINT}" stroke-width="1" stroke-opacity="0.65"/>')
    o.append(f'<g filter="url(#hand)" fill="none" stroke="{INK}" stroke-linecap="round" '
             f'stroke-linejoin="round" transform="translate({W/2:.1f},64) scale(1.75)">'
             f'{icon_fn()}</g>')
    o.append(f'<text x="{W/2}" y="146" font-family="{MONO}" font-size="52" font-weight="600" '
             f'text-anchor="middle" fill="{INK}" letter-spacing="-1">{data.get(key,0):,}</text>')
    o.append(f'<text x="{W/2}" y="176" font-family="{SF}" font-size="15.5" font-weight="500" '
             f'text-anchor="middle" fill="{MUTED}">{label}</text>')
    if sub:
        o.append(f'<text x="{W/2}" y="195" font-family="{SF}" font-size="12" '
                 f'text-anchor="middle" fill="{FAINT}">{sub}</text>')
    o.append(stamp(W, H, when, pad_x=20, pad_y=20))   # inside the tile border
    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    d = collect()
    when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("stats:", {k: d[k] for k in sorted(d)})
    os.makedirs(OUTDIR, exist_ok=True)
    if "--tiles" in sys.argv:
        for i, key in enumerate(STATS, 1):
            p = os.path.join(OUTDIR, f"stats-{i}-{key}.svg")
            open(p, "w").write(render_tile(key, d, when))
            print("wrote", p)
    else:
        p = os.path.join(OUTDIR, "stats.svg")
        open(p, "w").write(render_row(d, when))
        print("wrote", p)
