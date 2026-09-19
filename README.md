# My Feeds

A static daily snapshot of the weekly top 10 posts from
[`r/SideProject`](https://www.reddit.com/r/SideProject/).

## Setup

1. Request non-commercial Reddit Data API access and register an OAuth app by
   following [Reddit's access guidance](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data).
2. Add these repository secrets in GitHub under **Settings > Secrets and
   variables > Actions**:
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`
   - `REDDIT_USER_AGENT`, using Reddit's descriptive format, for example
     `github-actions:personal-feeds:v1.0 (by /u/your_username)`
3. In **Settings > Pages**, select **GitHub Actions** as the deployment source.
4. Run **Update feed** manually once from the Actions tab.

The workflow refreshes the site daily at 08:17 UTC. GitHub schedules are
best-effort and public repositories can have schedules disabled after 60 days
without repository activity. The manual workflow trigger remains available.

## Local checks

```sh
python3 generate.py --self-test
```

To build with live data, export the three Reddit variables listed above and
run `python3 generate.py`. The generated site is written to `_site/`.
