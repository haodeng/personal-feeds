#!/usr/bin/env python3
"""Build the static My Feeds page from Reddit's public Atom feed."""

from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

SUBREDDIT = "SideProject"
OUTPUT_DIR = Path("_site")
REDDIT_ORIGIN = "https://www.reddit.com"
FEED_URL = f"{REDDIT_ORIGIN}/r/{SUBREDDIT}/top/.rss?t=week&limit=25"
USER_AGENT = "github-actions:personal-feeds:v1.0 (+https://github.com/haodeng/personal-feeds)"
ATOM = "{http://www.w3.org/2005/Atom}"


def fetch_posts() -> list[dict]:
    request = Request(FEED_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            root = ElementTree.parse(response).getroot()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Reddit returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError, ElementTree.ParseError) as error:
        raise RuntimeError(f"Reddit request failed: {error}") from error

    posts = []
    for entry in root.findall(f"{ATOM}entry"):
        link = entry.find(f"{ATOM}link")
        posts.append(
            {
                "title": entry.findtext(f"{ATOM}title", ""),
                "url": link.get("href", "") if link is not None else "",
                "published": entry.findtext(f"{ATOM}published", ""),
            }
        )
    return posts


def select_posts(posts: list[dict]) -> list[dict]:
    selected = []
    for post in posts:
        title = str(post.get("title", "")).strip()
        parsed = urlparse(str(post.get("url", "")))
        host = (parsed.hostname or "").lower()
        if not title or title.lower() in {"[deleted]", "[removed]"}:
            continue
        if parsed.scheme != "https" or not (host == "reddit.com" or host.endswith(".reddit.com")):
            continue
        selected.append(post)
        if len(selected) == 10:
            break
    if not selected:
        raise RuntimeError("Reddit returned no publishable posts")
    return selected


def format_date(timestamp: str) -> str:
    date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return f"{date.strftime('%b')} {date.day}, {date.year}"


def render_card(post: dict, rank: int) -> str:
    title = html.escape(str(post["title"]))
    permalink = html.escape(str(post["url"]), quote=True)
    lead_class = " feed-card--lead" if rank == 1 else ""
    created = format_date(str(post["published"]))

    return f"""
      <li class="feed-card{lead_class}">
        <span class="rank" aria-label="Rank {rank}">{rank:02d}</span>
        <article>
          <div class="post-meta"><time>{created}</time></div>
          <h2><a href="{permalink}" rel="external nofollow noreferrer">{title}</a></h2>
          <div class="post-footer">
            <a href="{permalink}" rel="external nofollow noreferrer">Open discussion</a>
          </div>
        </article>
      </li>"""


def render_page(posts: list[dict], updated_at: datetime) -> str:
    cards = "\n".join(render_card(post, rank) for rank, post in enumerate(posts, 1))
    updated_iso = updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    updated_label = updated_at.astimezone(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="The weekly top 10 posts from r/SideProject, refreshed daily.">
  <meta name="color-scheme" content="light dark">
  <title>My Feeds | r/SideProject</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f3f2ee;
      --surface: #fbfaf7;
      --surface-strong: #e8e5dd;
      --text: #20201e;
      --muted: #66645f;
      --line: #d5d2c9;
      --accent: #a43b17;
      --accent-soft: #f3d7c9;
      --radius: 18px;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #171715;
        --surface: #20201d;
        --surface-strong: #2b2a26;
        --text: #f1efe8;
        --muted: #aaa79e;
        --line: #3a3934;
        --accent: #ff8a5c;
        --accent-soft: #512718;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    a {{ color: inherit; }}
    a:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 4px; border-radius: 3px; }}
    .shell {{ width: min(1180px, calc(100% - 40px)); margin: 0 auto; }}
    .site-header {{ display: flex; align-items: center; justify-content: space-between; min-height: 72px; border-bottom: 1px solid var(--line); }}
    .brand {{ font-size: 1rem; font-weight: 760; letter-spacing: -0.02em; text-decoration: none; }}
    .source-link {{ color: var(--muted); font-size: 0.88rem; text-underline-offset: 4px; }}
    .hero {{ padding: clamp(64px, 9vw, 112px) 0 48px; max-width: 850px; }}
    .eyebrow {{ margin: 0 0 18px; color: var(--accent); font-size: 0.76rem; font-weight: 760; letter-spacing: 0.13em; text-transform: uppercase; }}
    h1 {{ margin: 0; max-width: 780px; font-size: clamp(3.1rem, 8vw, 6.8rem); line-height: 0.91; letter-spacing: -0.065em; font-weight: 760; }}
    .hero-copy {{ margin: 26px 0 0; max-width: 560px; color: var(--muted); font-size: clamp(1.05rem, 2vw, 1.25rem); line-height: 1.55; }}
    .update-line {{ display: flex; flex-wrap: wrap; gap: 10px 20px; align-items: center; margin-top: 28px; color: var(--muted); font-size: 0.82rem; }}
    .stale-warning {{ margin: 0 0 28px; padding: 14px 18px; border: 1px solid var(--accent); border-radius: var(--radius); background: var(--accent-soft); color: var(--text); }}
    .stale-warning[hidden] {{ display: none; }}
    .feed-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; padding: 0; margin: 0 0 96px; list-style: none; }}
    .feed-card {{ position: relative; min-height: 290px; padding: 26px; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }}
    .feed-card--lead {{ grid-column: 1 / -1; min-height: 370px; padding: clamp(28px, 5vw, 54px); background: var(--surface-strong); }}
    .rank {{ display: block; margin-bottom: 50px; color: var(--accent); font-variant-numeric: tabular-nums; font-size: 0.86rem; font-weight: 760; }}
    .post-meta {{ min-height: 24px; display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; color: var(--muted); font-size: 0.76rem; }}
    h2 {{ margin: 12px 0 30px; max-width: 26ch; font-size: clamp(1.35rem, 2.4vw, 2rem); line-height: 1.08; letter-spacing: -0.035em; }}
    .feed-card--lead h2 {{ max-width: 20ch; font-size: clamp(2rem, 5vw, 4.6rem); }}
    h2 a {{ text-decoration-thickness: 1px; text-decoration-color: transparent; text-underline-offset: 0.14em; transition: color 160ms ease, text-decoration-color 160ms ease; }}
    h2 a:hover {{ color: var(--accent); text-decoration-color: currentColor; }}
    .post-footer {{ margin-top: auto; font-size: 0.78rem; }}
    .post-footer a {{ color: var(--accent); font-weight: 720; text-underline-offset: 4px; }}
    .feed-card article {{ min-height: calc(100% - 66px); display: flex; flex-direction: column; }}
    .site-footer {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; padding: 28px 0 42px; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.78rem; }}
    .site-footer p {{ margin: 0; }}
    @media (max-width: 720px) {{
      .shell {{ width: min(100% - 28px, 1180px); }}
      .site-header {{ min-height: 64px; }}
      .hero {{ padding: 58px 0 38px; }}
      h1 {{ font-size: clamp(3rem, 16vw, 5rem); }}
      .feed-grid {{ grid-template-columns: 1fr; margin-bottom: 64px; }}
      .feed-card--lead {{ grid-column: auto; min-height: 330px; }}
      .feed-card {{ min-height: 270px; padding: 24px; }}
      .rank {{ margin-bottom: 38px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ scroll-behavior: auto !important; transition-duration: 0.01ms !important; }}
    }}
  </style>
</head>
<body>
  <header class="shell site-header">
    <a class="brand" href="./">My Feeds</a>
    <a class="source-link" href="https://www.reddit.com/r/{SUBREDDIT}/" rel="external nofollow noreferrer">r/{SUBREDDIT}</a>
  </header>
  <main class="shell">
    <section class="hero" aria-labelledby="page-title">
      <p class="eyebrow">Weekly top 10</p>
      <h1 id="page-title">What builders shipped this week.</h1>
      <p class="hero-copy">A daily snapshot of the projects earning attention in r/{SUBREDDIT}.</p>
      <div class="update-line">
        <span>Updated <time id="updated-at" datetime="{updated_iso}">{updated_label}</time></span>
        <span>Ranked by Reddit's weekly top feed</span>
      </div>
    </section>
    <p class="stale-warning" id="stale-warning" role="status" hidden>This feed is more than 48 hours old. The last successful snapshot remains available.</p>
    <ol class="feed-grid" aria-label="Top posts from r/{SUBREDDIT}">
{cards}
    </ol>
  </main>
  <footer class="shell site-footer">
    <p>Data from Reddit. Not affiliated with Reddit.</p>
    <p><a href="https://www.reddit.com/r/{SUBREDDIT}/" rel="external nofollow noreferrer">Visit r/{SUBREDDIT}</a></p>
  </footer>
  <script>
    const updatedAt = Date.parse(document.querySelector("#updated-at").dateTime);
    if (Date.now() - updatedAt > 48 * 60 * 60 * 1000) {{
      document.querySelector("#stale-warning").hidden = false;
    }}
  </script>
</body>
</html>
"""


def self_test() -> None:
    valid = {
        "title": "A useful <project>",
        "url": "https://www.reddit.com/r/SideProject/comments/abc/useful/",
        "published": "2026-09-19T08:00:00+00:00",
    }
    posts = [
        {**valid, "title": "[deleted]"},
        {**valid, "url": "https://example.com/not-reddit"},
        valid,
    ]
    assert select_posts(posts) == [valid]
    page = render_page([valid], datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert "A useful &lt;project&gt;" in page and "<project>" not in page
    assert "Open discussion" in page and 'id="stale-warning"' in page


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0

    try:
        posts = select_posts(fetch_posts())
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "index.html").write_text(
            render_page(posts, datetime.now(timezone.utc)), encoding="utf-8"
        )
        (OUTPUT_DIR / ".nojekyll").touch()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1

    print(f"Built {OUTPUT_DIR / 'index.html'} with {len(posts)} posts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
