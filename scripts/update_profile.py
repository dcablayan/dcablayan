#!/usr/bin/env python3
"""Generate Andrew6rant-style light/dark GitHub profile cards.

Visual reference: https://github.com/Andrew6rant/Andrew6rant
"""

from __future__ import annotations

import calendar
import html
import json
import os
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
USERNAME = "dcablayan"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"{USERNAME}-profile-readme",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def request_json(url: str, *, payload: dict | None = None) -> dict | list:
    body = json.dumps(payload).encode() if payload else None
    request = urllib.request.Request(url, data=body, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def github_data() -> dict:
    user = request_json(f"https://api.github.com/users/{USERNAME}")
    repos = request_json(
        f"https://api.github.com/users/{USERNAME}/repos?per_page=100&type=owner"
    )
    owned_repos = [repo for repo in repos if not repo["fork"]]

    languages: Counter[str] = Counter()
    for repo in owned_repos:
        languages.update(request_json(repo["languages_url"]))

    metrics = {
        "contributions": 0,
        "contributed_repos": len(owned_repos),
        "commits": 0,
        "stars": sum(repo["stargazers_count"] for repo in owned_repos),
        "added": 0,
        "deleted": 0,
    }
    if TOKEN:
        query = """
        query($login: String!, $authorId: ID!) {
          user(login: $login) {
            contributionCalendar: contributionsCollection {
              contributionCalendar { totalContributions }
            }
            repositoriesContributedTo(
              first: 1,
              contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY],
              includeUserRepositories: true
            ) { totalCount }
            repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {
              nodes {
                stargazerCount
                defaultBranchRef {
                  target {
                    ... on Commit {
                      history(first: 100, author: {id: $authorId}) {
                        totalCount
                        nodes { additions deletions }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        result = request_json(
            "https://api.github.com/graphql",
            payload={
                "query": query,
                "variables": {"login": USERNAME, "authorId": user["node_id"]},
            },
        )["data"]["user"]
        histories = [
            repo.get("defaultBranchRef", {}).get("target", {}).get("history", {})
            for repo in result["repositories"]["nodes"]
            if repo.get("defaultBranchRef")
        ]
        metrics = {
            "contributions": result["contributionCalendar"]["contributionCalendar"]["totalContributions"],
            "contributed_repos": result["repositoriesContributedTo"]["totalCount"],
            "commits": sum(history.get("totalCount", 0) for history in histories),
            "stars": sum(repo["stargazerCount"] for repo in result["repositories"]["nodes"]),
            "added": sum(commit["additions"] for history in histories for commit in history.get("nodes", [])),
            "deleted": sum(commit["deletions"] for history in histories for commit in history.get("nodes", [])),
        }

    return {"user": user, "languages": languages, "metrics": metrics}


def ascii_portrait(
    path: Path, width: int = 45, height: int = 25
) -> list[str]:
    # Character cells are roughly twice as tall as they are wide, so 45x25
    # produces a portrait-shaped image in a 16px monospace terminal grid.
    glyphs = "  .,:;irsXA253hMHGS#9B&@"
    with Image.open(path) as source:
        source = source.convert("L")
        crop = (
            round(source.width * 0.17),
            round(source.height * 0.01),
            round(source.width * 0.83),
            round(source.height * 0.72),
        )
        image = source.crop(crop).resize((width, height), Image.Resampling.LANCZOS)
        image = ImageOps.autocontrast(image, cutoff=1)
        image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=175, threshold=2))
        image = ImageEnhance.Contrast(image).enhance(1.15)
        pixels = list(image.getdata())
        return [
            "".join(
                glyphs[(255 - pixel) * (len(glyphs) - 1) // 255]
                for pixel in pixels[offset : offset + width]
            ).rstrip()
            for offset in range(0, width * height, width)
        ]


def account_uptime(created_at: str) -> str:
    start = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    today = date.today()
    years = today.year - start.year
    if (today.month, today.day) < (start.month, start.day):
        years -= 1
    anchor_year = start.year + years
    anchor_day = min(start.day, calendar.monthrange(anchor_year, start.month)[1])
    anchor = date(anchor_year, start.month, anchor_day)
    months = (today.year - anchor.year) * 12 + today.month - anchor.month
    if today.day < anchor.day:
        months -= 1
    month_number = anchor.month - 1 + months
    month_year = anchor.year + month_number // 12
    month = month_number % 12 + 1
    day = min(anchor.day, calendar.monthrange(month_year, month)[1])
    month_anchor = date(month_year, month, day)
    days = (today - month_anchor).days
    return f"{years} years, {months} months, {days} days"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def span(css_class: str | None, value: object) -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    return f"<tspan{class_attr}>{esc(value)}</tspan>"


def kv(label: str, value: object, width: int) -> list[tuple[str | None, str]]:
    value = str(value)
    prefix_length = len(label) + 3  # leading dot/space and colon
    dots = max(1, width - prefix_length - len(value) - 2)
    return [
        ("cc", ". "),
        ("key", label),
        (None, ":"),
        ("cc", " " + "." * dots + " "),
        ("value", value),
    ]


def svg_row(y: int, segments: list[tuple[str | None, str]]) -> str:
    return f'<tspan x="390" y="{y}">' + "".join(
        span(css_class, value) for css_class, value in segments
    ) + "</tspan>"


def section(y: int, title: str) -> str:
    rule = "—" * max(1, 57 - len(title))
    return svg_row(y, [(None, f"- {title} -{rule}--")])


def render_svg(data: dict, theme: str) -> str:
    user = data["user"]
    metrics = data["metrics"]
    languages = [name for name, _ in data["languages"].most_common(3)]
    language_text = ", ".join(languages) or "Python, TypeScript, JavaScript, Swift"
    total_loc = metrics["added"] - metrics["deleted"]

    themes = {
        "dark": {
            "background": "#161b22",
            "text": "#c9d1d9",
            "key": "#ffa657",
            "value": "#a5d6ff",
            "add": "#3fb950",
            "delete": "#f85149",
            "cc": "#616e7f",
        },
        "light": {
            "background": "#f6f8fa",
            "text": "#24292f",
            "key": "#953800",
            "value": "#0a3069",
            "add": "#1a7f37",
            "delete": "#cf222e",
            "cc": "#c2cfde",
        },
    }
    colors = themes[theme]

    portrait = "\n".join(
        f'<tspan x="15" y="{30 + index * 20}">{esc(line)}</tspan>'
        for index, line in enumerate(ascii_portrait(ROOT / "assets" / "portrait.jpg"))
    )

    repo_stats = kv("Repos", user["public_repos"], 18)
    if metrics["contributed_repos"]:
        repo_stats += [
            (None, " {"),
            ("key", "Contributed"),
            (None, ": "),
            ("value", str(metrics["contributed_repos"])),
            (None, "}"),
        ]
    if metrics["stars"]:
        repo_stats += [
            (None, " | "),
            ("key", "Stars"),
            (None, ": "),
            ("value", str(metrics["stars"])),
        ]

    activity_stats = kv("Commits", f'{metrics["commits"]:,}', 21)
    if metrics["contributions"]:
        activity_stats += [
            (None, " | "),
            ("key", "Contributions"),
            (None, ": "),
            ("value", f'{metrics["contributions"]:,}'),
        ]
    if user["followers"]:
        activity_stats += [
            (None, " | "),
            ("key", "Followers"),
            (None, ": "),
            ("value", f'{user["followers"]:,}'),
        ]

    loc_stats = kv("Lines of Code on GitHub", f"{total_loc:,}", 38)
    loc_changes: list[tuple[str | None, str]] = []
    if metrics["added"]:
        loc_changes.append(("addColor", f'{metrics["added"]:,}++'))
    if metrics["deleted"]:
        if loc_changes:
            loc_changes.append((None, ", "))
        loc_changes.append(("delColor", f'{metrics["deleted"]:,}--'))
    if loc_changes:
        loc_stats += [(None, " ( ")] + loc_changes + [(None, " )")]

    rows = [
        svg_row(30, [(None, "dylan@cablayan -" + "—" * 45 + "--")]),
        svg_row(50, kv("OS", "macOS, iOS", 59)),
        svg_row(70, kv("Uptime", account_uptime(user["created_at"]), 59)),
        svg_row(90, kv("Host", "OpenAI & HTDC", 59)),
        svg_row(110, kv("Kernel", "UHM '29 | ex-NASA", 59)),
        svg_row(130, kv("IDE", "Codex, VS Code, Xcode", 59)),
        svg_row(150, [("cc", ". ")]),
        svg_row(170, kv("Languages.Programming", language_text, 59)),
        svg_row(190, kv("Languages.Computer", "HTML, CSS, SQL, Markdown", 59)),
        svg_row(210, kv("Languages.Real", "English", 59)),
        svg_row(230, [("cc", ". ")]),
        svg_row(250, kv("Hobbies.Software", "AI tools, web apps, open source", 59)),
        svg_row(270, kv("Hobbies.Hardware", "Robotics, Formula 1", 59)),
        section(310, "Contact"),
        svg_row(330, kv("Email.Personal", "dcablayan07@gmail.com", 59)),
        svg_row(350, kv("Website", "dylancablayan.vercel.app", 59)),
        svg_row(370, kv("LinkedIn", "in/dylancablayan", 59)),
        svg_row(390, kv("X", "@dylancablayan", 59)),
        svg_row(410, kv("Location", "Honolulu, Hawaii", 59)),
        section(450, "GitHub Stats"),
        svg_row(470, repo_stats),
        svg_row(490, activity_stats),
        svg_row(510, loc_stats),
    ]

    return f'''<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" width="985px" height="530px" font-size="16px" role="img" aria-labelledby="title desc">
<title id="title">Dylan Cablayan's GitHub profile</title>
<desc id="desc">ASCII portrait, personal details, contact links, and live GitHub statistics.</desc>
<style>
@font-face {{
  src: local('Consolas'), local('Consolas Bold');
  font-family: 'ConsolasFallback';
  font-display: swap;
  -webkit-size-adjust: 109%;
  size-adjust: 109%;
}}
.key {{fill: {colors['key']};}}
.value {{fill: {colors['value']};}}
.addColor {{fill: {colors['add']};}}
.delColor {{fill: {colors['delete']};}}
.cc {{fill: {colors['cc']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="985px" height="530px" fill="{colors['background']}" rx="15"/>
<text x="15" y="30" fill="{colors['text']}" class="ascii" font-size="13.5px">
{portrait}
</text>
<text x="390" y="30" fill="{colors['text']}" font-size="15px">
{chr(10).join(rows)}
</text>
</svg>
'''


def main() -> None:
    data = github_data()
    for theme in ("dark", "light"):
        output = ROOT / f"{theme}_mode.svg"
        output.write_text(render_svg(data, theme), encoding="utf-8")
        print(f"updated {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
