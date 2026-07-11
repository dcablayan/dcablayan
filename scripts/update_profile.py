#!/usr/bin/env python3
"""Generate the terminal-style profile card from GitHub data and a portrait."""

from __future__ import annotations

import html
import json
import os
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


ROOT = Path(__file__).resolve().parents[1]
USERNAME = "dcablayan"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"{USERNAME}-profile-readme",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    API_HEADERS["Authorization"] = f"Bearer {TOKEN}"


def request_json(url: str, *, payload: dict | None = None) -> dict | list:
    data = json.dumps(payload).encode() if payload else None
    request = urllib.request.Request(url, data=data, headers=API_HEADERS)
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
        repo_languages = request_json(repo["languages_url"])
        languages.update(repo_languages)

    contributions = {
        "total": 0,
        "commits": 0,
        "issues": 0,
        "pull_requests": 0,
    }
    if TOKEN:
        query = """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              contributionCalendar { totalContributions }
              totalCommitContributions
              totalIssueContributions
              totalPullRequestContributions
            }
          }
        }
        """
        result = request_json(
            "https://api.github.com/graphql",
            payload={"query": query, "variables": {"login": USERNAME}},
        )
        collection = result["data"]["user"]["contributionsCollection"]
        contributions = {
            "total": collection["contributionCalendar"]["totalContributions"],
            "commits": collection["totalCommitContributions"],
            "issues": collection["totalIssueContributions"],
            "pull_requests": collection["totalPullRequestContributions"],
        }

    return {
        "user": user,
        "repos": owned_repos,
        "languages": languages,
        "contributions": contributions,
    }


def ascii_portrait(path: Path, width: int = 60, height: int = 39) -> list[str]:
    chars = "  ..,:;irsXA253hMHGS#9B&@"
    with Image.open(path) as source:
        image = ImageOps.fit(source.convert("L"), (width, height))
        image = ImageOps.autocontrast(image, cutoff=1)
        image = ImageEnhance.Contrast(image).enhance(1.35)
        # Dark source pixels become dense glyphs; the light background disappears.
        return [
            "".join(chars[(255 - pixel) * (len(chars) - 1) // 255] for pixel in row)
            for row in (list(image.getdata())[i : i + width] for i in range(0, width * height, width))
        ]


def fmt(value: int) -> str:
    return f"{value:,}"


def svg_text(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_svg(data: dict) -> str:
    user = data["user"]
    contributions = data["contributions"]
    portrait = ascii_portrait(ROOT / "assets" / "portrait.jpg")
    top_languages = data["languages"].most_common(4)
    language_total = sum(count for _, count in top_languages) or 1
    language_colors = {
        "Python": "#3572A5",
        "TypeScript": "#3178C6",
        "JavaScript": "#F1E05A",
        "HTML": "#E34C26",
        "CSS": "#663399",
        "Swift": "#F05138",
        "C++": "#F34B7D",
    }

    portrait_lines = "\n".join(
        f'<tspan x="42" dy="14">{svg_text(line)}</tspan>' for line in portrait
    )

    stats = [
        ("Contributions (12 mo)", fmt(contributions["total"])),
        ("Public repositories", fmt(user["public_repos"])),
        ("Followers / following", f'{fmt(user["followers"])} / {fmt(user["following"])}'),
        ("Pull requests", fmt(contributions["pull_requests"])),
        ("Issues", fmt(contributions["issues"])),
        ("Member since", datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).strftime("%b %Y")),
    ]
    stat_lines = "\n".join(
        f'<tspan x="682" dy="31"><tspan fill="#7ee787">{svg_text(label.ljust(25))}</tspan>'
        f'<tspan fill="#e6edf3">{svg_text(value)}</tspan></tspan>'
        for label, value in stats
    )

    language_x = 682
    language_blocks: list[str] = []
    for name, count in top_languages:
        width = round(405 * count / language_total, 1)
        color = language_colors.get(name, "#8b949e")
        language_blocks.append(
            f'<rect x="{language_x}" y="484" width="{width}" height="8" fill="{color}" />'
        )
        language_x += width
    language_labels = "  ·  ".join(name for name, _ in top_languages)

    bio = (user.get("bio") or "building useful things").strip()

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="620" viewBox="0 0 1200 620" role="img" aria-labelledby="title desc">
  <title id="title">Dylan Cablayan's GitHub profile</title>
  <desc id="desc">An ASCII portrait beside live GitHub profile statistics.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#070a0f"/>
      <stop offset="1" stop-color="#0d1117"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2.5" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <rect width="1200" height="620" rx="18" fill="url(#bg)"/>
  <rect x="1" y="1" width="1198" height="618" rx="17" fill="none" stroke="#30363d"/>
  <circle cx="25" cy="25" r="6" fill="#ff5f57"/>
  <circle cx="45" cy="25" r="6" fill="#febc2e"/>
  <circle cx="65" cy="25" r="6" fill="#28c840"/>
  <text x="600" y="30" text-anchor="middle" fill="#8b949e" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">dcablayan — profile</text>
  <line x1="0" y1="48" x2="1200" y2="48" stroke="#21262d"/>

  <text x="42" y="72" fill="#39d0d8" opacity="0.94" filter="url(#glow)" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10.7" xml:space="preserve">{portrait_lines}</text>
  <line x1="635" y1="76" x2="635" y2="557" stroke="#21262d"/>

  <text x="682" y="106" fill="#f0f6fc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="28" font-weight="700">{svg_text(user["name"])}</text>
  <text x="682" y="136" fill="#39d0d8" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="16">@{svg_text(user["login"])}</text>
  <text x="682" y="170" fill="#8b949e" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">{svg_text(bio)}</text>
  <line x1="682" y1="194" x2="1137" y2="194" stroke="#30363d"/>

  <text x="682" y="221" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="14" xml:space="preserve">{stat_lines}</text>

  <text x="682" y="461" fill="#f0f6fc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">TOP LANGUAGES</text>
  <g>{''.join(language_blocks)}</g>
  <text x="682" y="516" fill="#8b949e" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">{svg_text(language_labels)}</text>

  <text x="682" y="557" fill="#39d0d8" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">Honolulu, Hawaiʻi  •  building at the edge of AI</text>
  <text x="1158" y="596" text-anchor="end" fill="#484f58" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10">auto-refreshed daily</text>
</svg>
'''


def main() -> None:
    output = ROOT / "assets" / "profile-card.svg"
    output.write_text(render_svg(github_data()), encoding="utf-8")
    print(f"updated {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
