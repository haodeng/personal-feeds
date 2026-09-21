# My Feeds

A static daily snapshot of the weekly top 10 posts from
[`r/SideProject`](https://www.reddit.com/r/SideProject/) and the daily top 10
repositories from [GitHub Trending](https://github.com/trending?since=daily)
and [GitHub Trending 中文](https://github.com/trending?since=daily&spoken_language_code=zh),
plus Show HN and V2EX Hot Topics. Danish News is a separate page with the
latest 10 headlines from DR Nyheder and TV 2.

## Setup

1. In **Settings > Pages**, select **GitHub Actions** as the deployment source.
2. Run **Update feed** manually once from the Actions tab.

No accounts, API applications, or repository secrets are required. The
generator reads Reddit's public weekly top Atom feed, GitHub's public daily
Trending pages, Hacker News's public Show HN API, V2EX's public Hot Topics
API, DR Nyheder's public RSS feed, and TV 2's public news page and article
metadata.

Each source is cached independently after a successful read. A first run still
fails if any source cannot be fetched; later runs can publish a validated,
visibly marked last-known-good snapshot for only the unavailable source.

The workflow refreshes the site daily at 08:17 UTC. GitHub schedules are
best-effort and public repositories can have schedules disabled after 60 days
without repository activity. The manual workflow trigger remains available.

## Local checks

```sh
python3 generate.py --self-test
```

Run `python3 generate.py` to build with live data. The generated site is written
to `_site/`.
