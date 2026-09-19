# My Feeds agent guide

## Product contract

My Feeds is a non-commercial static GitHub Pages site. It publishes the weekly
top 10 eligible posts from `r/SideProject` and the daily top 10 repositories
from GitHub Trending using a daily GitHub Actions build.

- Fetch Reddit's public weekly top Atom feed and publish the first 10 valid,
  non-deleted entries.
- Fetch GitHub's public daily Trending page and publish its first 10 valid
  repositories with their stars-today count.
- Keep the page text-first. Do not publish usernames, thumbnails, analytics,
  cookies, search, pagination, or client-side Reddit requests.
- Keep each future source separate. Add abstractions only when a second source
  actually exists.

## Implementation constraints

- Keep the project dependency-free: Python standard library, HTML, CSS, and the
  existing tiny stale-data script.
- Treat `generate.py` as the source of the site. `_site/` is generated output
  and remains untracked.
- Keep both fetches credential-free. Use the public Atom feed, public Trending
  page, and a descriptive fixed user agent.
- Fail before deployment when fetching or validation fails. This preserves the
  last successful GitHub Pages deployment.
- Preserve accessible semantic HTML, keyboard focus styles, responsive layouts,
  system light/dark themes, and reduced-motion handling.

Read [README.md](README.md) when changing setup, deployment, the feed source,
or the refresh schedule.

## Change workflow

1. Trace the affected path through `generate.py` and the Pages workflow.
2. Make the smallest change that preserves the product contract.
3. Run:

   ```sh
   python3 generate.py --self-test
   python3 -m py_compile generate.py
   ```

4. For markup or style changes, render synthetic data locally and inspect both
   desktop and mobile layouts in light and dark mode. Never commit synthetic
   posts as current content.

A change is complete when the checks pass, secrets cannot reach the generated
page, failure still leaves the previous deployment intact, and relevant setup
instructions remain accurate.
