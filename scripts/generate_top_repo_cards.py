#!/usr/bin/env python3
"""Generate SVG cards for the owner's most-starred repositories.

Ranks non-fork, non-archived public repos by stars and writes one card per
repo to top-repos-output/card-N.svg (N=1 is the most-starred). The README
references those fixed paths, so the ranking can change without an edit.

Palette matches the tokyonight theme already used by profile-summary-cards.
"""

import html
import json
import os
import sys
import urllib.error
import urllib.request

USERNAME = os.environ.get("GH_USERNAME", "omgits0mar")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "top-repos-output")
CARD_COUNT = int(os.environ.get("CARD_COUNT", "5"))

# tokyonight, identical to the profile-summary-card output already in this repo
BG = "#1a1b27"
TITLE = "#70a5fd"
TEXT = "#38bdae"
ICON = "#bf91f3"

WIDTH = 400
HEIGHT = 130
PAD = 25

# GitHub's linguist colors for the languages that show up here; anything
# unmapped falls back to the icon color rather than disappearing.
LANG_COLORS = {
    "C": "#555555",
    "C#": "#178600",
    "C++": "#f34b7d",
    "CSS": "#563d7c",
    "Dockerfile": "#384d54",
    "Go": "#00ADD8",
    "HTML": "#e34c26",
    "Java": "#b07219",
    "JavaScript": "#f1e05a",
    "Jupyter Notebook": "#DA5B0B",
    "Lua": "#000080",
    "Makefile": "#427819",
    "Python": "#3572A5",
    "Rust": "#dea584",
    "Shell": "#89e051",
    "TypeScript": "#3178c6",
}

STAR_PATH = (
    "M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279"
    "l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 "
    "01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A"
    ".75.75 0 018 .25z"
)
FORK_PATH = (
    "M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm-.75 2.122a2.25 2.25 0 10-1.5 0"
    "v.878A2.25 2.25 0 004.75 8.5h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 "
    "2.25 0 002.25-2.25v-.878a2.25 2.25 0 10-1.5 0v.878a.75.75 0 01-.75.75h-4.5A"
    ".75.75 0 015 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm3-"
    "8.75a.75.75 0 100-1.5.75.75 0 000 1.5z"
)


def fetch_repos(username):
    """Return all public non-fork, non-archived repos for username."""
    repos, page = [], 1
    token = os.environ.get("GITHUB_TOKEN")
    while True:
        url = (
            f"https://api.github.com/users/{username}/repos"
            f"?per_page=100&page={page}&type=owner"
        )
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                batch = json.load(resp)
        except urllib.error.HTTPError as exc:
            sys.exit(f"GitHub API error {exc.code} fetching page {page}: {exc.read()[:200]!r}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    return [
        r
        for r in repos
        if not r["fork"] and not r["archived"] and r["name"].lower() != username.lower()
    ]


def rank(repos, count):
    """Most stars first. Forks then recency break ties so output is stable."""
    ordered = sorted(
        repos,
        key=lambda r: (r["stargazers_count"], r["forks_count"], r["pushed_at"]),
        reverse=True,
    )
    return ordered[:count]


def wrap(text, max_chars, max_lines):
    """Greedy word wrap, ellipsizing whatever overflows the last line."""
    if not text:
        return []
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        if len(lines) == max_lines:
            break
        # A single word longer than the line gets hard-cut.
        current = word if len(word) <= max_chars else word[: max_chars - 1] + "…"
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(lines)) < len(text):
        last = lines[-1]
        if len(last) > max_chars - 1:
            last = last[: max_chars - 1].rstrip()
        lines[-1] = last + "…"
    return lines


def humanize(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def fit_title(name, max_width=WIDTH - 2 * PAD, base_size=17, min_size=13):
    """Pick the largest font size at which the repo name still fits.

    Repo names here run to 41 characters, which overruns the card at the base
    size. Shrink first (a slightly smaller name beats a cropped one), and only
    ellipsize if the floor still isn't enough.

    Returns (display_name, font_size).
    """
    # Bold Segoe UI averages ~0.55em per character across this name set.
    def width_at(text, size):
        return len(text) * size * 0.55

    for size in range(base_size, min_size - 1, -1):
        if width_at(name, size) <= max_width:
            return name, size

    budget = int(max_width / (min_size * 0.55))
    return name[: max(1, budget - 1)] + "…", min_size


def render(repo):
    name = repo["name"]
    display_name, title_size = fit_title(name)
    desc_lines = wrap(repo.get("description") or "", max_chars=52, max_lines=2)
    lang = repo.get("language")
    lang_color = LANG_COLORS.get(lang, ICON)
    stars = humanize(repo["stargazers_count"])
    forks = humanize(repo["forks_count"])

    alt = f"{name}: {repo.get('description') or 'no description'}. {repo['stargazers_count']} stars."

    desc_svg = "".join(
        f'<text x="{PAD}" y="{62 + i * 18}" class="desc">{html.escape(line)}</text>'
        for i, line in enumerate(desc_lines)
    )

    # Footer sits at a fixed baseline so cards stay the same height whether the
    # description ran to one line or two.
    fy = 108
    footer = f"""
  <g transform="translate({PAD}, {fy - 11})">
    <circle cx="6" cy="6" r="6" fill="{lang_color}"/>
    <text x="19" y="10" class="meta">{html.escape(lang or "—")}</text>
  </g>
  <g transform="translate({PAD + 140}, {fy - 12})">
    <path d="{STAR_PATH}" fill="{ICON}" transform="scale(0.82)"/>
    <text x="18" y="11" class="meta">{stars}</text>
  </g>
  <g transform="translate({PAD + 210}, {fy - 12})">
    <path d="{FORK_PATH}" fill="{ICON}" transform="scale(0.82)"/>
    <text x="18" y="11" class="meta">{forks}</text>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" fill="none" role="img" aria-label="{html.escape(alt)}">
  <title>{html.escape(alt)}</title>
  <style>
    .title {{ font: 600 {title_size}px 'Segoe UI', Ubuntu, Sans-Serif; fill: {TITLE}; }}
    .desc  {{ font: 400 13px 'Segoe UI', Ubuntu, Sans-Serif; fill: {TEXT}; }}
    .meta  {{ font: 400 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {TEXT}; }}
  </style>
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="6" fill="{BG}" stroke="{TITLE}" stroke-opacity="0.3"/>
  <text x="{PAD}" y="36" class="title">{html.escape(display_name)}</text>
{desc_svg}
{footer}
</svg>
"""


def markdown_block(top):
    """Card grid: the top repo full-width, the rest two-up.

    Each card links to its own repo, so this has to be regenerated alongside
    the SVGs — otherwise a ranking change leaves the links pointing at the
    wrong repos.
    """
    base = f"https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/main/{OUTPUT_DIR}"

    def card(repo, index, width):
        alt = html.escape(repo["name"], quote=True)
        return (
            f'<a href="{repo["html_url"]}">'
            f'<img width="{width}" alt="{alt}" src="{base}/card-{index}.svg"/></a>'
        )

    rows = [card(top[0], 1, "62%")]
    for start in range(1, len(top), 2):
        pair = [card(r, start + i + 1, "49%") for i, r in enumerate(top[start : start + 2])]
        rows.append("\n".join(pair))

    return "<div align=\"center\">\n\n" + "\n\n".join(rows) + "\n\n</div>"


def update_readme(path, block):
    """Replace the content between the top-repos markers, in place."""
    start, end = "<!-- top-repos:start -->", "<!-- top-repos:end -->"
    with open(path, encoding="utf-8") as fh:
        readme = fh.read()

    if start not in readme or end not in readme:
        sys.exit(f"{path} is missing the {start} / {end} markers.")

    head, rest = readme.split(start, 1)
    _, tail = rest.split(end, 1)
    updated = f"{head}{start}\n\n{block}\n\n{end}{tail}"

    if updated == readme:
        print(f"{path} already current")
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"{path} updated")


def main():
    top = rank(fetch_repos(USERNAME), CARD_COUNT)
    if not top:
        sys.exit("No eligible repositories found.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for i, repo in enumerate(top, start=1):
        path = os.path.join(OUTPUT_DIR, f"card-{i}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(repo))
        print(f"{path}  <-  {repo['name']} ({repo['stargazers_count']}*)")

    update_readme(os.environ.get("README_PATH", "README.md"), markdown_block(top))


if __name__ == "__main__":
    main()
