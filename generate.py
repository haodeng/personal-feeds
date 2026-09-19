#!/usr/bin/env python3
"""Build the static My Feeds page from Reddit's OAuth API."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

SUBREDDIT = "SideProject"
OUTPUT_DIR = Path("_site")
REDDIT_ORIGIN = "https://www.reddit.com"


def request_json(request: Request) -> dict:
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Reddit returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Reddit request failed: {error}") from error


def fetch_posts(client_id: str, client_secret: str, user_agent: str) -> list[dict]:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    token_request = Request(
        f"{REDDIT_ORIGIN}/api/v1/access_token",
        data=urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": user_agent,
        },
        method="POST",
    )
    token = request_json(token_request).get("access_token")
    if not token:
        raise RuntimeError("Reddit did not return an OAuth access token")

    listing_request = Request(
        f"https://oauth.reddit.com/r/{SUBREDDIT}/top?t=week&limit=25&raw_json=1",
        headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent},
    )
    payload = request_json(listing_request)
    try:
        return [child["data"] for child in payload["data"]["children"]]
    except (KeyError, TypeError) as error:
        raise RuntimeError("Reddit returned an unexpected listing response") from error


def select_posts(posts: list[dict]) -> list[dict]:
    selected = []
    for post in posts:
        title = str(post.get("title", "")).strip()
        if (
            not title
            or title.lower() in {"[deleted]", "[removed]"}
            or post.get("stickied")
            or post.get("over_18")
            or post.get("removed_by_category")
        ):
            continue
        selected.append(post)
        if len(selected) == 10:
            break
    if not selected:
        raise RuntimeError("Reddit returned no publishable posts")
    return selected


def safe_external_url(post: dict) -> str | None:
    if post.get("is_self"):
        return None
    url = str(post.get("url_overridden_by_dest") or post.get("url") or "")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return None
    if host == "redd.it" or host.endswith(".redd.it") or host == "reddit.com" or host.endswith(".reddit.com"):
        return None
    return url


def format_date(timestamp: int | float) -> str:
    date = datetime.fromtimestamp(timestamp, timezone.utc)
    return f"{date.strftime('%b')} {date.day}, {date.year}"


def render_card(post: dict, rank: int) -> str:
    title = html.escape(str(post["title"]))
    permalink = html.escape(f"{REDDIT_ORIGIN}{post.get('permalink', '')}", quote=True)
    flair = str(post.get("link_flair_text") or "").strip()
    flair_html = f'<span class="flair">{html.escape(flair)}</span>' if flair else ""
    external_url = safe_external_url(post)
    project_link = (
        f'<a class="project-link" href="{html.escape(external_url, quote=True)}" rel="external nofollow noreferrer">Visit project</a>'
        if external_url
        else ""
    )
    lead_class = " feed-card--lead" if rank == 1 else ""
    score = max(0, int(post.get("score") or 0))
    comments = max(0, int(post.get("num_comments") or 0))
    created = format_date(float(post.get("created_utc") or 0))

    return f"""
      <li class="feed-card{lead_class}">
        <span class="rank" aria-label="Rank {rank}">{rank:02d}</span>
        <article>
          <div class="post-meta">{flair_html}<time>{created}</time></div>
          <h2><a href="{permalink}" rel="external nofollow noreferrer">{title}</a></h2>
          <div class="post-footer">
            <div class="metrics" aria-label="Reddit activity">
              <span>{score:,} points</span>
              <span>{comments:,} comments</span>
            </div>
            <div class="post-links">
              <a href="{permalink}" rel="external nofollow noreferrer">Discussion</a>
              {project_link}
            </div>
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
    .flair {{ color: var(--text); font-weight: 700; }}
    h2 {{ margin: 12px 0 30px; max-width: 26ch; font-size: clamp(1.35rem, 2.4vw, 2rem); line-height: 1.08; letter-spacing: -0.035em; }}
    .feed-card--lead h2 {{ max-width: 20ch; font-size: clamp(2rem, 5vw, 4.6rem); }}
    h2 a {{ text-decoration-thickness: 1px; text-decoration-color: transparent; text-underline-offset: 0.14em; transition: color 160ms ease, text-decoration-color 160ms ease; }}
    h2 a:hover {{ color: var(--accent); text-decoration-color: currentColor; }}
    .post-footer {{ display: flex; flex-wrap: wrap; gap: 14px 28px; align-items: center; justify-content: space-between; margin-top: auto; }}
    .metrics, .post-links {{ display: flex; flex-wrap: wrap; gap: 10px 18px; font-size: 0.78rem; }}
    .metrics {{ color: var(--muted); }}
    .post-links a {{ color: var(--accent); font-weight: 720; text-underline-offset: 4px; }}
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
      .post-footer {{ align-items: flex-start; flex-direction: column; }}
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
        "permalink": "/r/SideProject/comments/abc/useful/",
        "url": "https://example.com",
        "score": 42,
        "num_comments": 7,
        "created_utc": 1_700_000_000,
    }
    posts = [
        {**valid, "title": "Pinned", "stickied": True},
        {**valid, "title": "Unsafe", "over_18": True},
        valid,
    ]
    assert select_posts(posts) == [valid]
    assert safe_external_url(valid) == "https://example.com"
    assert safe_external_url({**valid, "url": "https://www.reddit.com/x"}) is None
    page = render_page([valid], datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert "A useful &lt;project&gt;" in page and "<project>" not in page
    assert "Visit project" in page and 'id="stale-warning"' in page


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0

    required = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        posts = select_posts(
            fetch_posts(
                os.environ["REDDIT_CLIENT_ID"],
                os.environ["REDDIT_CLIENT_SECRET"],
                os.environ["REDDIT_USER_AGENT"],
            )
        )
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
