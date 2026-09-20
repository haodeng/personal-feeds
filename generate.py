#!/usr/bin/env python3
"""Build the static My Feeds page from public Reddit and GitHub feeds."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

SUBREDDIT = "SideProject"
OUTPUT_DIR = Path("_site")
CACHE_DIR = Path(".feed-cache")
REDDIT_ORIGIN = "https://www.reddit.com"
FEED_URL = f"{REDDIT_ORIGIN}/r/{SUBREDDIT}/top/.rss?t=week&limit=25"
GITHUB_ORIGIN = "https://github.com"
GITHUB_TRENDING_URL = f"{GITHUB_ORIGIN}/trending?since=daily"
GITHUB_TRENDING_ZH_URL = f"{GITHUB_TRENDING_URL}&spoken_language_code=zh"
HACKER_NEWS_ORIGIN = "https://hacker-news.firebaseio.com/v0"
HACKER_NEWS_SHOW_URL = f"{HACKER_NEWS_ORIGIN}/showstories.json"
HACKER_NEWS_ITEM_URL = f"{HACKER_NEWS_ORIGIN}/item/{{}}.json"
HACKER_NEWS_DISCUSSION_URL = "https://news.ycombinator.com/item?id={}"
V2EX_HOT_URL = "https://www.v2ex.com/api/topics/hot.json"
USER_AGENT = "github-actions:personal-feeds:v1.0 (+https://github.com/haodeng/personal-feeds)"
ATOM = "{http://www.w3.org/2005/Atom}"


class TrendingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.repos: list[dict] = []
        self._article_depth = 0
        self._repo_url = ""
        self._article_text: list[str] = []
        self._in_heading = False
        self._description_depth = 0
        self._description: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "article" and "Box-row" in attributes.get("class", "").split():
            self._article_depth = 1
            self._repo_url = ""
            self._article_text = []
            self._description_depth = 0
            self._description = []
            return
        if not self._article_depth:
            return
        self._article_depth += 1
        if self._description_depth:
            self._description_depth += 1
        elif tag == "p" and {"col-9", "color-fg-muted"}.issubset(
            attributes.get("class", "").split()
        ):
            self._description_depth = 1
        if tag == "h2":
            self._in_heading = True
        elif tag == "a" and self._in_heading:
            href = attributes.get("href", "")
            parts = href.strip("/").split("/")
            if href.startswith("/") and len(parts) == 2 and all(parts):
                self._repo_url = f"{GITHUB_ORIGIN}{href}"

    def handle_endtag(self, tag: str) -> None:
        if not self._article_depth:
            return
        if tag == "h2":
            self._in_heading = False
        if self._description_depth:
            self._description_depth -= 1
        self._article_depth -= 1
        if self._article_depth == 0 and self._repo_url:
            stars = re.search(r"([\d,]+)\s+stars today", " ".join(self._article_text))
            if stars:
                self.repos.append(
                    {
                        "name": self._repo_url.removeprefix(f"{GITHUB_ORIGIN}/"),
                        "url": self._repo_url,
                        "stars_today": stars.group(1),
                        "description": re.sub(
                            r"\s+([,.;:!?])", r"\1", " ".join(" ".join(self._description).split())
                        ),
                    }
                )

    def handle_data(self, data: str) -> None:
        if self._article_depth:
            self._article_text.append(data)
        if self._description_depth:
            self._description.append(data)


def load_source(key: str, fetcher, cache_dir: Path = CACHE_DIR) -> dict:
    cache_file = cache_dir / f"{key}.json"
    try:
        items = fetcher()
    except RuntimeError as error:
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            updated_at = datetime.fromisoformat(str(cached["updated_at"]))
            if updated_at.tzinfo is None or not isinstance(cached["items"], list):
                raise ValueError("invalid snapshot")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise error
        print(f"{key} fetch failed; using its last known good snapshot", file=sys.stderr)
        return {"items": cached["items"], "updated_at": updated_at, "stale": True}

    updated_at = datetime.now(timezone.utc)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"items": items, "updated_at": updated_at.isoformat()}), encoding="utf-8"
    )
    return {"items": items, "updated_at": updated_at, "stale": False}


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


def fetch_json(url: str, name: str):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{name} returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{name} request failed: {error}") from error


def fetch_trending_repos(url: str, name: str) -> list[dict]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            page = response.read().decode(response.headers.get_content_charset() or "utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{name} returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError, UnicodeDecodeError) as error:
        raise RuntimeError(f"{name} request failed: {error}") from error

    parser = TrendingParser()
    parser.feed(page)
    parser.close()
    if not parser.repos:
        raise RuntimeError(f"{name} returned no publishable repositories")
    return parser.repos[:10]


def select_show_hn(items: list[object]) -> list[dict]:
    selected = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "story" or item.get("dead") or item.get("deleted"):
            continue
        title = str(item.get("title", "")).strip()
        identifier = item.get("id")
        if not title or not isinstance(identifier, int):
            continue
        selected.append({"title": title, "url": HACKER_NEWS_DISCUSSION_URL.format(identifier)})
        if len(selected) == 10:
            break
    if not selected:
        raise RuntimeError("Hacker News returned no publishable Show HN stories")
    return selected


def fetch_show_hn() -> list[dict]:
    story_ids = fetch_json(HACKER_NEWS_SHOW_URL, "Hacker News")
    if not isinstance(story_ids, list):
        raise RuntimeError("Hacker News returned an invalid Show HN story list")
    items = [
        fetch_json(HACKER_NEWS_ITEM_URL.format(story_id), "Hacker News")
        for story_id in story_ids[:25]
        if isinstance(story_id, int)
    ]
    return select_show_hn(items)


def select_v2ex_topics(topics: object) -> list[dict]:
    if not isinstance(topics, list):
        raise RuntimeError("V2EX returned an invalid Hot Topics list")
    selected = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        title = str(topic.get("title", "")).strip()
        url = str(topic.get("url", "")).strip()
        node = topic.get("node")
        node_title = str(node.get("title", "")).strip() if isinstance(node, dict) else ""
        parsed = urlparse(url)
        if not title or parsed.scheme != "https" or parsed.hostname != "www.v2ex.com":
            continue
        selected.append({"title": title, "url": url, "meta": node_title})
        if len(selected) == 10:
            break
    if not selected:
        raise RuntimeError("V2EX returned no publishable Hot Topics")
    return selected


def fetch_v2ex_topics() -> list[dict]:
    return select_v2ex_topics(fetch_json(V2EX_HOT_URL, "V2EX"))


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


def render_source_status(source: dict) -> str:
    updated_at = source["updated_at"].astimezone(timezone.utc)
    label = updated_at.strftime("%b %d, %Y at %H:%M UTC")
    updated_iso = updated_at.isoformat().replace("+00:00", "Z")
    state = " · Stale, last known good snapshot" if source["stale"] else ""
    return f'<p class="source-status">Updated <time datetime="{updated_iso}">{label}</time>{state}</p>'


def render_card(post: dict, rank: int) -> str:
    title = html.escape(str(post["title"]))
    permalink = html.escape(str(post["url"]), quote=True)
    created = format_date(str(post["published"]))

    return f"""
      <li class="feed-row">
        <span class="rank" aria-label="Rank {rank}">{rank:02d}</span>
        <article>
          <div class="post-meta"><time>{created}</time></div>
          <h2><a href="{permalink}" rel="external nofollow noreferrer">{title}</a></h2>
          <div class="post-footer">
            <a href="{permalink}" rel="external nofollow noreferrer">Open discussion</a>
          </div>
        </article>
      </li>"""


def render_repo_card(repo: dict, rank: int) -> str:
    name = html.escape(str(repo["name"]))
    url = html.escape(str(repo["url"]), quote=True)
    stars = html.escape(str(repo["stars_today"]))
    description = html.escape(str(repo["description"]))
    return f"""
      <li class="feed-row">
        <span class="rank" aria-label="Rank {rank}">{rank:02d}</span>
        <article>
          <div class="post-meta">{stars} stars today</div>
          <h3><a href="{url}" rel="external nofollow noreferrer">{name}</a></h3>
          <p class="repo-description">{description}</p>
          <div class="post-footer">
            <a href="{url}" rel="external nofollow noreferrer">View repository</a>
          </div>
        </article>
      </li>"""


def render_news_card(item: dict, rank: int) -> str:
    title = html.escape(str(item["title"]))
    url = html.escape(str(item["url"]), quote=True)
    meta = html.escape(str(item.get("meta", "")))
    meta_html = f'<div class="post-meta">{meta}</div>' if meta else ""
    return f"""
      <li class="feed-row">
        <span class="rank" aria-label="Rank {rank}">{rank:02d}</span>
        <article>
          {meta_html}
          <h3><a href="{url}" rel="external nofollow noreferrer">{title}</a></h3>
          <div class="post-footer"><a href="{url}" rel="external nofollow noreferrer">Open discussion</a></div>
        </article>
      </li>"""


def render_page(
    posts: list[dict],
    repos: list[dict],
    chinese_repos: list[dict],
    show_hn: list[dict],
    v2ex_topics: list[dict],
    source_statuses: dict[str, dict],
    updated_at: datetime,
) -> str:
    reddit_cards = "\n".join(render_card(post, rank) for rank, post in enumerate(posts, 1))
    github_cards = "\n".join(render_repo_card(repo, rank) for rank, repo in enumerate(repos, 1))
    chinese_github_cards = "\n".join(
        render_repo_card(repo, rank) for rank, repo in enumerate(chinese_repos, 1)
    )
    show_hn_cards = "\n".join(render_news_card(item, rank) for rank, item in enumerate(show_hn, 1))
    v2ex_cards = "\n".join(render_news_card(topic, rank) for rank, topic in enumerate(v2ex_topics, 1))
    updated_iso = updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    updated_label = updated_at.astimezone(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")
    reddit_status = render_source_status(source_statuses["reddit"])
    github_status = render_source_status(source_statuses["github"])
    github_zh_status = render_source_status(source_statuses["github_zh"])
    show_hn_status = render_source_status(source_statuses["show_hn"])
    v2ex_status = render_source_status(source_statuses["v2ex"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Daily snapshots of what builders and developers are discussing.">
  <meta name="color-scheme" content="light dark">
  <title>My Feeds</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f6f2;
      --surface: #efede7;
      --surface-strong: #e6e3db;
      --text: #24231f;
      --muted: #615f58;
      --line: #d8d5cc;
      --accent: #a43b17;
      --accent-soft: #f3d7c9;
      --radius: 18px;
    }}
    :root[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #151613;
      --surface: #20211d;
      --surface-strong: #2a2b25;
      --text: #f5f3ec;
      --muted: #b7b4aa;
      --line: #3e3f38;
      --accent: #ff8a5c;
      --accent-soft: #512718;
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme]) {{
        color-scheme: dark;
        --bg: #151613;
        --surface: #20211d;
        --surface-strong: #2a2b25;
        --text: #f5f3ec;
        --muted: #b7b4aa;
        --line: #3e3f38;
        --accent: #ff8a5c;
        --accent-soft: #512718;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    a {{ color: inherit; }}
    a:focus-visible, button:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 4px; border-radius: 3px; }}
    .shell {{ width: min(1240px, calc(100% - 40px)); margin: 0 auto; }}
    .site-header {{ display: flex; align-items: center; justify-content: space-between; min-height: 60px; border-bottom: 1px solid var(--line); }}
    .brand {{ font-size: 1rem; font-weight: 760; letter-spacing: -0.02em; text-decoration: none; }}
    .header-actions {{ display: flex; flex: 1; min-width: 0; align-items: center; justify-content: flex-end; gap: 14px; }}
    .source-links {{ display: flex; min-width: 0; flex-wrap: wrap; justify-content: flex-end; gap: 8px 16px; }}
    .source-link {{ color: var(--muted); font-size: 0.88rem; text-underline-offset: 4px; white-space: nowrap; }}
    .theme-toggle {{ padding: 6px 9px; border: 1px solid var(--line); border-radius: 999px; background: transparent; color: var(--text); font: inherit; font-size: 0.78rem; font-weight: 720; cursor: pointer; }}
    .theme-toggle:hover {{ background: var(--surface); }}
    .hero {{ padding: clamp(32px, 4vw, 52px) 0 24px; max-width: 760px; }}
    .eyebrow {{ margin: 0 0 18px; color: var(--accent); font-size: 0.76rem; font-weight: 760; letter-spacing: 0.13em; text-transform: uppercase; }}
    h1 {{ margin: 0; max-width: 700px; font-size: clamp(2.45rem, 4.2vw, 4rem); line-height: 0.98; letter-spacing: -0.05em; font-weight: 760; }}
    .hero-copy {{ margin: 12px 0 0; max-width: 560px; color: var(--muted); font-size: 1rem; line-height: 1.55; }}
    .update-line {{ display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center; margin-top: 14px; color: var(--muted); font-size: 0.82rem; }}
    .stale-warning {{ margin: 0 0 20px; padding: 14px 18px; border: 1px solid var(--accent); border-radius: var(--radius); background: var(--accent-soft); color: var(--text); }}
    .stale-warning[hidden] {{ display: none; }}
    .jump-bar {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 28px; }}
    .jump-bar a {{ padding: 6px 10px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); font-size: 0.8rem; font-weight: 700; text-decoration: none; }}
    .jump-bar a:hover {{ background: var(--surface); color: var(--text); }}
    .feeds-layout {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 56px; margin-bottom: 56px; }}
    .feed-section {{ scroll-margin-top: 20px; }}
    .section-heading {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: baseline; gap: 4px 20px; margin: 0 0 12px; }}
    .section-heading h2 {{ grid-column: 1; margin: 0; max-width: none; font-size: clamp(1.5rem, 3vw, 2.4rem); }}
    .section-heading > p {{ grid-column: 2; margin: 0; color: var(--muted); font-size: 0.88rem; text-align: right; }}
    .section-heading .source-status {{ grid-column: 1 / -1; color: var(--muted); font-size: 0.74rem; text-align: left; }}
    .feed-grid {{ margin: 0; padding: 0; border-top: 1px solid var(--line); list-style: none; }}
    .feed-row {{ display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 12px; margin: 0 -10px; padding: 16px 10px; border-bottom: 1px solid var(--line); border-radius: 8px; }}
    .feed-row:hover {{ background: var(--surface); }}
    .feed-row:active {{ background: var(--surface-strong); }}
    .rank {{ color: var(--accent); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-variant-numeric: tabular-nums; font-size: 0.78rem; font-weight: 760; }}
    .post-meta {{ display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; color: var(--muted); font-size: 0.8rem; }}
    .feed-row h2, .feed-row h3 {{ margin: 7px 0 8px; max-width: 42ch; font-size: clamp(1.18rem, 1.7vw, 1.52rem); line-height: 1.18; letter-spacing: -0.028em; }}
    .feed-row h2 a, .feed-row h3 a {{ text-decoration-thickness: 1px; text-decoration-color: transparent; text-underline-offset: 0.14em; transition: color 160ms ease, text-decoration-color 160ms ease; }}
    .feed-row h2 a:hover, .feed-row h3 a:hover {{ color: var(--accent); text-decoration-color: currentColor; }}
    .post-footer {{ font-size: 0.8rem; }}
    .repo-description {{ margin: 0 0 10px; max-width: 70ch; color: var(--muted); font-size: 0.92rem; line-height: 1.5; }}
    .post-footer a {{ color: var(--accent); font-weight: 720; text-underline-offset: 4px; }}
    .feed-section--wide {{ grid-column: 1 / -1; }}
    .feed-section--wide .feed-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 56px; }}
    .site-footer {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; padding: 28px 0 42px; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.78rem; }}
    .site-footer p {{ margin: 0; }}
    @media (max-width: 720px) {{
      .shell {{ width: min(100% - 28px, 1180px); }}
      .site-header {{ min-height: 56px; padding: 10px 0; }}
      .header-actions {{ align-items: flex-start; }}
      .hero {{ padding: 32px 0 22px; }}
      h1 {{ font-size: clamp(2.45rem, 13vw, 3.5rem); }}
      .feed-row {{ grid-template-columns: 34px minmax(0, 1fr); gap: 8px; padding: 14px 0; }}
      .feeds-layout {{ grid-template-columns: 1fr; gap: 44px; margin-bottom: 44px; }}
      .feed-section--wide {{ grid-column: auto; }}
      .feed-section--wide .feed-grid {{ display: block; }}
      .section-heading {{ grid-template-columns: 1fr; }}
      .section-heading > p {{ grid-column: auto; text-align: left; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ scroll-behavior: auto !important; transition-duration: 0.01ms !important; }}
    }}
  </style>
</head>
<body>
  <header class="shell site-header">
    <a class="brand" href="./">My Feeds</a>
    <div class="header-actions">
      <nav class="source-links" aria-label="Sources">
        <a class="source-link" href="https://www.reddit.com/r/{SUBREDDIT}/" rel="external nofollow noreferrer">r/{SUBREDDIT}</a>
        <a class="source-link" href="{GITHUB_TRENDING_URL}" rel="external nofollow noreferrer">GitHub Trending</a>
        <a class="source-link" href="https://github.com/trending?since=daily&amp;spoken_language_code=zh" rel="external nofollow noreferrer">GitHub Trending 中文</a>
        <a class="source-link" href="https://news.ycombinator.com/show" rel="external nofollow noreferrer">Show HN</a>
        <a class="source-link" href="https://www.indiehackers.com/" rel="external nofollow noreferrer">Indie Hackers</a>
        <a class="source-link" href="https://www.producthunt.com/" rel="external nofollow noreferrer">Product Hunt</a>
        <a class="source-link" href="https://www.v2ex.com/" rel="external nofollow noreferrer">V2EX</a>
      </nav>
      <button class="theme-toggle" type="button" aria-pressed="false">Theme</button>
    </div>
  </header>
  <main class="shell">
    <section class="hero" aria-labelledby="page-title">
      <p class="eyebrow">Daily top 10</p>
      <h1 id="page-title">What builders are watching.</h1>
      <p class="hero-copy">A daily snapshot from five developer communities.</p>
      <div class="update-line">
        <span>Updated <time id="updated-at" datetime="{updated_iso}">{updated_label}</time></span>
        <span>Five public sources, one quick read</span>
      </div>
    </section>
    <p class="stale-warning" id="stale-warning" role="status" hidden>This feed is more than 48 hours old. The last successful snapshot remains available.</p>
    <nav class="jump-bar" aria-label="Jump to a feed">
      <a href="#sideproject">r/{SUBREDDIT}</a>
      <a href="#github-trending">GitHub</a>
      <a href="#github-trending-zh">GitHub 中文</a>
      <a href="#show-hn">Show HN</a>
      <a href="#v2ex">V2EX</a>
    </nav>
    <div class="feeds-layout">
      <section class="feed-section" id="sideproject" aria-labelledby="reddit-heading">
        <div class="section-heading">
          <h2 id="reddit-heading">r/{SUBREDDIT}</h2>
          <p>Weekly top posts</p>
          {reddit_status}
        </div>
        <ol class="feed-grid" aria-label="Top posts from r/{SUBREDDIT}">
{reddit_cards}
        </ol>
      </section>
      <section class="feed-section" id="github-trending" aria-labelledby="github-heading">
        <div class="section-heading">
          <h2 id="github-heading">GitHub Trending</h2>
          <p>Repositories gaining stars today</p>
          {github_status}
        </div>
        <ol class="feed-grid" aria-label="Trending GitHub repositories">
{github_cards}
        </ol>
      </section>
      <section class="feed-section feed-section--wide" id="github-trending-zh" aria-labelledby="github-zh-heading">
        <div class="section-heading">
          <h2 id="github-zh-heading">GitHub Trending 中文</h2>
          <p>Chinese-language repositories gaining stars today</p>
          {github_zh_status}
        </div>
        <ol class="feed-grid" aria-label="Trending Chinese-language GitHub repositories">
{chinese_github_cards}
        </ol>
      </section>
      <section class="feed-section" id="show-hn" aria-labelledby="show-hn-heading">
        <div class="section-heading">
          <h2 id="show-hn-heading">Show HN</h2>
          <p>New projects from Hacker News</p>
          {show_hn_status}
        </div>
        <ol class="feed-grid" aria-label="Hacker News Show HN stories">
{show_hn_cards}
        </ol>
      </section>
      <section class="feed-section" id="v2ex" aria-labelledby="v2ex-heading">
        <div class="section-heading">
          <h2 id="v2ex-heading">V2EX</h2>
          <p>Hot Topics</p>
          {v2ex_status}
        </div>
        <ol class="feed-grid" aria-label="V2EX Hot Topics">
{v2ex_cards}
        </ol>
      </section>
    </div>
  </main>
  <footer class="shell site-footer">
    <p>Data from Reddit, GitHub, Hacker News, and V2EX. Not affiliated with them.</p>
    <p><a href="{GITHUB_TRENDING_URL}" rel="external nofollow noreferrer">Visit GitHub Trending</a></p>
  </footer>
  <script>
    const themeToggle = document.querySelector(".theme-toggle");
    const savedTheme = localStorage.getItem("theme");
    const setTheme = (theme) => {{
      document.documentElement.dataset.theme = theme;
      localStorage.setItem("theme", theme);
      themeToggle.textContent = theme === "dark" ? "Dark" : "Light";
      themeToggle.setAttribute("aria-pressed", theme === "dark");
      themeToggle.setAttribute("aria-label", `Switch to ${{theme === "dark" ? "light" : "dark"}} theme`);
    }};
    setTheme(savedTheme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
    themeToggle.addEventListener("click", () => setTheme(
      document.documentElement.dataset.theme === "dark" ? "light" : "dark"
    ));
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
    parser = TrendingParser()
    parser.feed('''<article class="Box-row"><h2><a href="/octo/example">octo / example</a></h2><p class="col-9 color-fg-muted">Useful <em>project</em>.</p><span>1,234 stars today</span></article>''')
    assert parser.repos == [{"name": "octo/example", "url": "https://github.com/octo/example", "stars_today": "1,234", "description": "Useful project."}]
    show_hn = select_show_hn([{"id": 1, "type": "story", "title": "A Show HN project"}])
    v2ex = select_v2ex_topics([{"title": "A V2EX topic", "url": "https://www.v2ex.com/t/1", "node": {"title": "Tech"}}])
    checked_at = datetime(2026, 9, 19, tzinfo=timezone.utc)
    source_statuses = {
        key: {"updated_at": checked_at, "stale": key == "v2ex"}
        for key in ("reddit", "github", "github_zh", "show_hn", "v2ex")
    }
    page = render_page([valid], parser.repos, parser.repos, show_hn, v2ex, source_statuses, checked_at)
    assert "A useful &lt;project&gt;" in page and "<project>" not in page
    assert "last known good snapshot" in page and 'href="#show-hn"' in page and 'id="stale-warning"' in page
    with tempfile.TemporaryDirectory() as directory:
        cache_dir = Path(directory)
        fresh = load_source("sample", lambda: [valid], cache_dir)
        assert fresh["stale"] is False

        def fail():
            raise RuntimeError("temporary failure")

        cached = load_source("sample", fail, cache_dir)
        assert cached["items"] == [valid] and cached["stale"] is True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0

    try:
        sources = {
            "reddit": load_source("reddit", lambda: select_posts(fetch_posts())),
            "github": load_source("github", lambda: fetch_trending_repos(GITHUB_TRENDING_URL, "GitHub Trending")),
            "github_zh": load_source("github_zh", lambda: fetch_trending_repos(GITHUB_TRENDING_ZH_URL, "GitHub Trending 中文")),
            "show_hn": load_source("show_hn", fetch_show_hn),
            "v2ex": load_source("v2ex", fetch_v2ex_topics),
        }
        posts = sources["reddit"]["items"]
        repos = sources["github"]["items"]
        chinese_repos = sources["github_zh"]["items"]
        show_hn = sources["show_hn"]["items"]
        v2ex_topics = sources["v2ex"]["items"]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "index.html").write_text(
            render_page(posts, repos, chinese_repos, show_hn, v2ex_topics, sources, datetime.now(timezone.utc)), encoding="utf-8"
        )
        (OUTPUT_DIR / ".nojekyll").touch()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1

    print(
        f"Built {OUTPUT_DIR / 'index.html'} with {len(posts)} Reddit posts, {len(repos)} global repositories, "
        f"{len(chinese_repos)} Chinese-language repositories, {len(show_hn)} Show HN stories, and {len(v2ex_topics)} V2EX topics"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
