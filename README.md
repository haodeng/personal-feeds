# My Feeds

A static daily snapshot of the weekly top 10 posts from
[`r/SideProject`](https://www.reddit.com/r/SideProject/) and the daily top 10
repositories from [GitHub Trending](https://github.com/trending?since=daily).

## Setup

1. In **Settings > Pages**, select **GitHub Actions** as the deployment source.
2. Run **Update feed** manually once from the Actions tab.

No accounts, API applications, or repository secrets are required. The
generator reads Reddit's public weekly top Atom feed and GitHub's public daily
Trending page.

The workflow refreshes the site daily at 08:17 UTC. GitHub schedules are
best-effort and public repositories can have schedules disabled after 60 days
without repository activity. The manual workflow trigger remains available.

## Local checks

```sh
python3 generate.py --self-test
```

Run `python3 generate.py` to build with live data. The generated site is written
to `_site/`.
