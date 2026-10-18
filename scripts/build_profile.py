"""Regenerates the profile's data images and the "Now Building" table.

- assets/field-{day,night}.svg: a cross-section of the field. Languages are the
  plots on the surface, each year's commits a layer of soil underneath.
- assets/credits.svg: experience and community, rolling like film credits.
- README.md: the table between the recent:start / recent:end markers.

Runs daily from .github/workflows/profile.yml. Standard library only.
Locally: PROFILE_TOKEN=$(gh auth token) python scripts/build_profile.py

The token must be able to read Burak's private repositories, otherwise their
commits and languages are left out.
"""
import json
import os
import random
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from glyphs import Type

USER = "burakyalcin10"
# Burak also committed from a machine signed in to this account; those commits
# count as his when they are in his repositories.
EXTRA_AUTHORS = ["bahar6146"]
ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

# Markup, styling and build files say little about what someone codes in.
IGNORED_LANGUAGES = {"HTML", "CSS", "SCSS", "Sass", "Less", "Makefile", "Dockerfile",
                     "Shell", "Batchfile", "PowerShell", "Procfile"}
TOP_LANGUAGES = 5
RECENT_REPOS = 3

CREDITS = [
    ("Experience", [
        ("Part-time software engineer", "SAN TSG", "Oct 2025 – Jun 2026"),
        ("Software engineering intern", "SAN TSG", "Jul – Aug 2025"),
        ("Educator and mentor", "T3 Foundation", "Since Oct 2023"),
    ]),
    ("Community", [
        ("Chairman of the supervisory board,|former chairman of the board", "3Y",
         "Akdeniz Software, AI and Creativity community"),
        ("Vice president of the organizing committee", "BİLMÖK", ""),
        ("Organisation officer", "UBMK 2024", ""),
    ]),
    ("Education", [
        ("Computer engineering, 4th year", "Akdeniz University", "Antalya, GPA 3.30 / 4"),
    ]),
    ("Programs", [
        ("", "TÜBİTAK 2209-A", ""),
        ("", "Erasmus+ KA 154", ""),
        ("", "Savunma Sanayii 401", ""),
        ("", "T3 Foundation Educator Mentor Scholarship", ""),
    ]),
]

THEMES = {
    "day": {"sky": ["#c9d8df", "#dce5e6", "#eef0ea"], "ink": "#1e2a22", "ink2": "#4c5a50", "night": 0},
    "night": {"sky": ["#14212a", "#213238", "#46574f"], "ink": "#e7ece6", "ink2": "#a9b8ad", "night": 1},
}
SOIL = ["#3a2a21", "#5a4334", "#7b6049", "#6b5240", "#4e3a2d"]
STONE = ["#77736b", "#67635c", "#5a5650"]
TURF = ["#2f5b3b", "#355f3a"]
GREENS = ["#2f5b3b", "#3c6e47", "#28503a", "#4f7d4c", "#5f8a55"]
WOOD, WOOD_DARK = "#b08f6a", "#8a7258"


# ---------- data ----------
def graphql(query):
    token = os.environ.get("PROFILE_TOKEN") or os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": f"{USER}-profile"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch():
    logins = [USER, *EXTRA_AUTHORS]
    ids = graphql("{" + " ".join(f'a{i}: user(login: "{l}") {{ id }}' for i, l in enumerate(logins)) + "}")
    author_ids = [ids[f"a{i}"]["id"] for i in range(len(logins))]

    user = graphql(f"""{{
      user(login: "{USER}") {{
        createdAt
        repositories(ownerAffiliations: OWNER, isFork: false, first: 100,
                     orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
          nodes {{
            name url isPrivate pushedAt
            primaryLanguage {{ name }}
            languages(first: 20) {{ edges {{ size node {{ name }} }} }}
          }}
        }}
      }}
    }}""")["user"]
    repos = user["repositories"]["nodes"]
    years = list(range(int(user["createdAt"][:4]), datetime.now(timezone.utc).year + 1))

    def span(y):
        return f'since: "{y}-01-01T00:00:00Z", until: "{y + 1}-01-01T00:00:00Z"'

    # Commits on each owned repository's default branch, by Burak's accounts, per year.
    per_year = dict.fromkeys(years, 0)
    for start in range(0, len(repos), 8):
        chunk = repos[start:start + 8]
        fields = " ".join(f'y{y}a{i}: history({span(y)}, author: {{id: "{aid}"}}) {{ totalCount }}'
                          for y in years for i, aid in enumerate(author_ids))
        data = graphql("{" + " ".join(
            f'r{j}: repository(owner: "{USER}", name: "{r["name"]}") '
            f"{{ defaultBranchRef {{ target {{ ... on Commit {{ {fields} }} }} }} }}"
            for j, r in enumerate(chunk)) + "}")
        for j in range(len(chunk)):
            branch = data[f"r{j}"]["defaultBranchRef"]
            if branch:
                for y in years:
                    per_year[y] += sum(branch["target"][f"y{y}a{i}"]["totalCount"] for i in range(len(author_ids)))

    # Plus Burak's commits to repositories he does not own.
    others = graphql(f'{{ user(login: "{USER}") {{ ' + " ".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") '
        "{ commitContributionsByRepository(maxRepositories: 100) "
        "{ repository { owner { login } } contributions { totalCount } } }"
        for y in years) + " } }")["user"]
    for y in years:
        per_year[y] += sum(c["contributions"]["totalCount"] for c in others[f"y{y}"]["commitContributionsByRepository"]
                           if c["repository"]["owner"]["login"] != USER)
    return repos, per_year


def summarize(repos, per_year):
    sizes = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            lang = edge["node"]["name"]
            if lang not in IGNORED_LANGUAGES:
                sizes[lang] = sizes.get(lang, 0) + edge["size"]
    total = sum(sizes.values()) or 1
    public = [r for r in repos if not r["isPrivate"]]
    first = min((y for y, n in per_year.items() if n), default=max(per_year))
    return {
        "per_year": [(y, n) for y, n in sorted(per_year.items()) if y >= first],
        "commits": sum(per_year.values()),
        "public_repos": len(public),
        "languages": [(lang, size / total * 100) for lang, size in sorted(sizes.items(), key=lambda kv: -kv[1])[:TOP_LANGUAGES]],
        "recent": [r for r in public if r["name"] != USER][:RECENT_REPOS],
    }


# ---------- drawing ----------
def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def frame(width, height, sky, body, defs, title, desc, style=""):
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in zip(("0", ".55", "1"), sky))
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
<title id="title">{title}</title>
<desc id="desc">{desc}</desc>{style}
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">{stops}</linearGradient>
  <clipPath id="frame"><rect width="{width}" height="{height}" rx="16"/></clipPath>
  {defs}
</defs>
<g clip-path="url(#frame)">
  <rect width="{width}" height="{height}" fill="url(#sky)"/>
  {body}
</g>
</svg>
"""


def render_field(s, theme):
    t = THEMES[theme]
    dim = (lambda c: mix(c, "#132029", 0.35)) if t["night"] else (lambda c: c)
    rnd = random.Random(42)
    ty = Type()
    width, surface = 900, 132
    left, right = 26, 874  # the slab floats with sky on both sides, like the island
    out = []

    # plots: one per language, widths by share of code, wide enough for their name
    x0, x1 = 214, 852
    shares = [p for _, p in s["languages"]]
    mins = [max(56, ty.width(lang, "text-medium", 14) + 18) for lang, _ in s["languages"]]
    widths = [(x1 - x0) * p / sum(shares) for p in shares]
    for _ in range(4):  # give narrow plots their minimum, take it from the wide ones
        short = sum(max(0, m - w) for w, m in zip(widths, mins))
        roomy = sum(w for w, m in zip(widths, mins) if w > m)
        widths = [m if w <= m else w - short * w / roomy for w, m in zip(widths, mins)]
    edges = [x0]
    for w in widths:
        edges.append(edges[-1] + w)

    # soil: one layer per year, newest on top, thickness by commits
    years = list(reversed(s["per_year"]))
    peak = max((n for _, n in years), default=1) or 1
    y = surface + 12
    layers = []
    for i, (year, n) in enumerate(years):
        h = max(22, min(108, 108 * n / peak))
        layers.append((year, n, y, h, SOIL[i % len(SOIL)]))
        y += h
    soil_bottom = y

    if not t["night"]:
        out.append('<ellipse cx="560" cy="44" rx="170" ry="20" fill="#ffffff" opacity=".7" filter="url(#soft)"/>')
    for year, n, top, h, colour in layers:
        out.append(f'<rect x="{left}" y="{top:.1f}" width="{right - left}" height="{h + .5:.1f}" fill="{dim(colour)}"/>'
                   f'<rect x="{left}" y="{top:.1f}" width="{right - left}" height="1" fill="#ffffff" opacity=".07"/>')
    # stepped base, like the underside of the island
    y = soil_bottom
    for inset, colour in zip((14, 64, 150), STONE):
        out.append(f'<rect x="{left + inset}" y="{y:.1f}" width="{right - left - 2 * inset}" height="13" fill="{dim(colour)}"/>')
        y += 13
    height = round(y + 26)
    out.append(f'<rect x="{left}" y="{surface}" width="{right - left}" height="{soil_bottom - surface:.0f}" fill="url(#shade)"/>')

    pebbles = "".join(
        f'<ellipse cx="{rnd.uniform(left, right):.0f}" cy="{rnd.uniform(surface + 24, soil_bottom - 3):.0f}" '
        f'rx="{rnd.uniform(1, 2.6):.1f}" ry="{rnd.uniform(.6, 1.4):.1f}"/>' for _ in range(90))
    out.append(f'<g fill="{dim("#8f897e")}" opacity=".45">{pebbles}</g>')
    roots = []
    for _ in range(70):
        rx, depth = rnd.uniform(left + 6, right - 6), rnd.uniform(8, 30)
        roots.append(f"M{rx:.1f} {surface + 12}q{rnd.uniform(-5, 5):.1f} {depth * .5:.1f} {rnd.uniform(-3, 3):.1f} {depth:.1f}")
    out.append(f'<path d="{"".join(roots)}" stroke="{dim("#6b5240")}" stroke-width=".9" opacity=".7"/>')

    # turf: its top seen from above, its front edge, a lighter strip per plot
    out.append(f'<rect x="{left}" y="{surface - 7}" width="{right - left}" height="7" fill="{dim("#3c6e47")}"/>'
               f'<rect x="{left}" y="{surface}" width="{right - left}" height="12.5" fill="{dim(TURF[0])}"/>')
    for i, (a, b) in enumerate(zip(edges, edges[1:])):
        out.append(f'<rect x="{a:.1f}" y="{surface}" width="{b - a:.1f}" height="12.5" fill="{dim(TURF[i % 2])}"/>')
    blades = {c: [] for c in GREENS}
    for _ in range(620):
        bx, by = rnd.uniform(left + 2, right - 2), surface + rnd.uniform(-6, 2)
        hgt = rnd.uniform(3, 9)
        blades[rnd.choice(GREENS)].append(
            f"M{bx:.1f} {by:.1f}q{rnd.uniform(-1, 1):.1f} {-hgt * .6:.1f} {rnd.uniform(-2.4, 2.4):.1f} {-hgt:.1f}")
    out.append('<g fill="none" stroke-width="1.2" stroke-linecap="round">' + "".join(
        f'<path stroke="{dim(c)}" d="{"".join(p)}"/>' for c, p in blades.items()) + "</g>")

    # stakes on the plot boundaries, with the language above each plot
    for x in edges:
        out.append(f'<rect x="{x - 2.5:.1f}" y="{surface - 46}" width="5" height="52" fill="{dim(WOOD_DARK)}"/>'
                   f'<path fill="{dim(WOOD_DARK)}" d="M{x - 5.5:.1f} {surface - 43}v-7l3 -3h5l3 3v7z"/>')
    for (lang, pct), a, b in zip(s["languages"], edges, edges[1:]):
        mid = (a + b) / 2
        out.append(ty.text(lang, mid, surface - 40, "text-medium", 14, t["ink"], anchor="middle"))
        out.append(ty.text(f"{pct:.0f}%", mid, surface - 23, "text", 13.5, t["ink2"], anchor="middle"))

    # the year labels, written on the soil
    for year, n, top, h, _ in layers:
        base = top + h / 2 + 5
        out.append(ty.text(str(year), left + 22, base, "display", 15, "#eef0ea"))
        out.append(ty.text(f"{n} commits", left + 70, base, "text", 14, "#d8c8b4"))

    # a wooden sign with the total
    first_year = s["per_year"][0][0] if s["per_year"] else datetime.now().year
    out.append(f'<rect x="102" y="{surface - 72}" width="6" height="80" fill="{dim(WOOD_DARK)}"/>'
               f'<path fill="{dim(WOOD)}" stroke="{dim(WOOD_DARK)}" stroke-width="2" '
               f'd="M41 {surface - 116}h128l6 6v42l-6 6h-128l-6 -6v-42z"/>')
    out.append(ty.text(f"{s['commits']}", 105, surface - 86, "display", 26, "#1e2a22", anchor="middle"))
    out.append(ty.text(f"commits since {first_year}", 105, surface - 69, "text", 12.5, "#3b2f25", anchor="middle"))

    defs = (ty.defs()
            + '<filter id="soft" x="-40%" y="-200%" width="180%" height="500%"><feGaussianBlur stdDeviation="14"/></filter>'
            + '<linearGradient id="shade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff" stop-opacity=".06"/>'
            + '<stop offset=".5" stop-color="#ffffff" stop-opacity="0"/><stop offset="1" stop-color="#000000" stop-opacity=".22"/></linearGradient>')
    desc = (f"{s['commits']} commits since {first_year}: "
            + ", ".join(f"{n} in {y}" for y, n in s["per_year"])
            + ". Languages by code size: " + ", ".join(f"{l} {p:.0f}%" for l, p in s["languages"]) + ".")
    return frame(width, height, t["sky"], "\n".join(out), defs, "Burak's commits and languages", desc)


def render_credits():
    """Night sky between two black film bars; the credits roll upward."""
    ty = Type()
    width, height, bar = 900, 300, 30
    rows, y = [], 70
    rows.append(ty.text("Burak Yalçın", width / 2, y, "display", 40, "#ffffff", anchor="middle"))
    y += 60
    for heading, entries in CREDITS:
        y += 34
        rows.append(ty.text(heading, width / 2, y, "text-medium", 15, "#a9b8ad", anchor="middle"))
        y += 36
        for role, org, note in entries:
            if role:
                for k, line in enumerate(role.split("|")):
                    rows.append(ty.text(line, width / 2 - 20, y + k * 20, "text", 16, "#c9d3cb", anchor="end"))
                rows.append(ty.text(org, width / 2 + 20, y, "display-medium", 21, "#ffffff"))
                if note:
                    rows.append(ty.text(note, width / 2 + 20, y + 21, "text", 13.5, "#a9b8ad"))
                y += max(20 * len(role.split("|")), 21 + (19 if note else 0)) + 20
            else:
                rows.append(ty.text(org, width / 2, y, "display-medium", 19, "#ffffff", anchor="middle"))
                y += 32
    roll = y + 40
    seconds = round(roll / 26)
    travel = height - bar + roll
    lead = (height - bar - 95) / travel * seconds  # open with the title in the middle of the screen
    style = f"""
<style>
  .roll {{ animation: roll {seconds}s linear -{lead:.1f}s infinite; }}
  @keyframes roll {{ from {{ transform: translateY({height - bar}px); }} to {{ transform: translateY({-roll}px); }} }}
  @media (prefers-reduced-motion: reduce) {{ .roll {{ animation: none; }} }}
</style>"""
    body = (f'<g class="roll">{"".join(rows)}</g>'
            f'<rect width="{width}" height="{height}" fill="url(#fade)"/>'
            f'<rect width="{width}" height="{bar}" fill="#000"/><rect y="{height - bar}" width="{width}" height="{bar}" fill="#000"/>')
    fade = ('<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="{bar / height:.3f}" stop-color="#14212a"/><stop offset=".26" stop-color="#14212a" stop-opacity="0"/>'
            f'<stop offset=".74" stop-color="#2c3d3f" stop-opacity="0"/><stop offset="{1 - bar / height:.3f}" stop-color="#2c3d3f"/></linearGradient>')
    desc = "Credits for Burak Yalçın. " + " ".join(
        f"{heading}: " + "; ".join(", ".join(p.replace("|", " ") for p in e if p) for e in entries) + "."
        for heading, entries in CREDITS)
    return frame(width, height, ["#14212a", "#213238", "#2c3d3f"], body, ty.defs() + fade,
                 "Credits", desc, style)


def render_recent(repos):
    rows = ["| Project | Language | Last push |", "| --- | --- | --- |"]
    for r in repos:
        lang = (r["primaryLanguage"] or {}).get("name", "")
        rows.append(f"| [{r['name']}]({r['url']}) | {lang} | {r['pushedAt'][:10]} |")
    return "\n".join(rows)


def main():
    stats = summarize(*fetch())
    for theme in THEMES:
        (ROOT / "assets" / f"field-{theme}.svg").write_text(render_field(stats, theme), encoding="utf-8")
    (ROOT / "assets" / "credits.svg").write_text(render_credits(), encoding="utf-8")

    readme = README.read_text(encoding="utf-8")
    block = f"<!-- recent:start -->\n{render_recent(stats['recent'])}\n<!-- recent:end -->"
    readme = re.sub(r"<!-- recent:start -->.*?<!-- recent:end -->", lambda _: block, readme, flags=re.S)
    README.write_text(readme, encoding="utf-8")
    print(f"{stats['commits']} commits ({', '.join(f'{y}: {n}' for y, n in stats['per_year'])}), "
          f"languages: {', '.join(f'{l} {p:.0f}%' for l, p in stats['languages'])}")


if __name__ == "__main__":
    main()
