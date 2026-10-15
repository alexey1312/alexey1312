"""Fetches fresh numbers from GitHub into data/stats.json, data/repos.json and
data/calendar.json (the last 53 weeks of daily contributions).

Environment variables:
  PROFILE_TOKEN  optional token with read:user. It adds private contributions
                 to the stats and the city. Without it, GITHUB_TOKEN is used.
  GITHUB_TOKEN   the token that GitHub Actions gives (public data only).

If GitHub fails, the previous files stay, so a flaky API never blanks out the
profile.

The GitHub queries and the streak logic are ported from Giorgi Kobaidze's
fetch.py (github.com/georgekobaidze/georgekobaidze, MIT; see NOTICE).
"""
import datetime
import json
import os
import pathlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
PROFILE = json.loads((HERE / "profile.json").read_text())
USER = PROFILE["login"]
UA = f"{USER}-profile-updater"


def http_json(url, *, token, body=None, timeout=30):
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={"User-Agent": UA, "Accept": "application/json", "Authorization": f"bearer {token}"},
    )
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def graphql(token, query, variables=None):
    res = http_json("https://api.github.com/graphql", token=token, body={"query": query, "variables": variables or {}})
    if res.get("errors"):
        raise RuntimeError("GraphQL error: " + "; ".join(e.get("message", "?") for e in res["errors"]))
    return res["data"]


def load(name, default):
    try:
        return json.loads((DATA / name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def warn(msg):
    # "::warning::" shows the message as an annotation on the Actions run page.
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {msg}", file=sys.stderr)


PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    merged: pullRequests(states: MERGED) { totalCount }
    contributionsCollection { contributionYears }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        nameWithOwner
        stargazerCount
        forkCount
        isArchived
        languages(first: 20) { edges { size node { name } } }
        latestRelease { tagName publishedAt url }
      }
    }
  }
}"""

REPO_FIELDS = "nameWithOwner stargazerCount latestRelease { tagName publishedAt url }"


def years_query(years):
    parts = [f"""
    y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{
      contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
    }}""" for y in years]
    return "query($login: String!) {\n  user(login: $login) {" + "".join(parts) + "\n  }\n}"


def repos_query(names):
    parts = [f'  r{i}: repository(owner: "{o}", name: "{n}") {{ {REPO_FIELDS} }}'
             for i, (o, n) in enumerate(name.split("/") for name in names)]
    return "query {\n" + "\n".join(parts) + "\n}"


def streaks(days, today):
    """days: {date: count}. The current streak can end yesterday if today has no contributions yet."""
    longest = run = 0
    for d in sorted(d for d in days if d <= today):
        run = run + 1 if days[d] > 0 else 0
        longest = max(longest, run)
    current, d = 0, today
    if days.get(d, 0) == 0:
        d -= datetime.timedelta(days=1)
    while days.get(d, 0) > 0:
        current += 1
        d -= datetime.timedelta(days=1)
    return current, longest


def wanted_repos():
    """Every repository that a card or a button on the profile names."""
    items = PROFILE["projects"] + PROFILE["also"] + [PROFILE["highlight"]]
    return sorted({p["repo"] for p in items if p.get("repo")})


def contributor_rank(token, repo):
    """This user's place and commit count among the contributors of a repository."""
    rows = http_json(f"https://api.github.com/repos/{repo}/contributors?per_page=100", token=token)
    humans = [r for r in rows if r.get("type") == "User"]
    for i, r in enumerate(humans):
        if r["login"].lower() == USER.lower():
            return {"rank": i + 1, "commits": r["contributions"], "of": len(humans)}
    return None


def fetch_github(token, today):
    u = graphql(token, PROFILE_QUERY, {"login": USER})["user"]
    years = sorted(u["contributionsCollection"]["contributionYears"])
    ydata = graphql(token, years_query(years), {"login": USER})["user"] if years else {}

    days, contribs_all = {}, 0
    for y in years:
        cal = ydata[f"y{y}"]["contributionCalendar"]
        contribs_all += cal["totalContributions"]
        for w in cal["weeks"]:
            for day in w["contributionDays"]:
                days[datetime.date.fromisoformat(day["date"])] = day["contributionCount"]
    current, longest = streaks(days, today)
    # The last 53 weeks, from a Sunday, like the GitHub graph. The city uses it.
    start = today - datetime.timedelta(weeks=52)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)
    calendar = [[d.isoformat(), days.get(d, 0)]
                for d in (start + datetime.timedelta(days=i) for i in range((today - start).days + 1))]

    own = u["repositories"]["nodes"]
    langs = {}
    for r in own:
        for edge in r["languages"]["edges"]:
            langs[edge["node"]["name"]] = langs.get(edge["node"]["name"], 0) + edge["size"]

    names = {r["nameWithOwner"] for r in own}
    extra = [n for n in wanted_repos() if n not in names]
    found = graphql(token, repos_query(extra)).values() if extra else []
    repos = {}
    for r in [*own, *found]:
        if r:
            rel = r.get("latestRelease")
            repos[r["nameWithOwner"]] = {
                "stars": r["stargazerCount"],
                "release": rel and {"tag": rel["tagName"], "date": rel["publishedAt"][:10], "url": rel["url"]},
                "own": r["nameWithOwner"] in names,
                "archived": r.get("isArchived", False),
            }

    stats = {
        "created_at": u["createdAt"],
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "prs_merged": u["merged"]["totalCount"],
        "repo_count": u["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in own),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "year": today.year,
        "contributions_year": ydata.get(f"y{today.year}", {}).get("contributionCalendar", {}).get("totalContributions", 0),
        "contributions_all": contribs_all,
        "streak_current": current,
        "streak_longest": longest,
    }
    try:
        stats["highlight"] = contributor_rank(token, PROFILE["highlight"]["repo"])
    except Exception as ex:  # noqa: BLE001 — one missing row must not fail the run
        warn(f"contributor rank unavailable: {ex}")
    return stats, calendar, dict(sorted(repos.items()))


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    token = os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("error: set PROFILE_TOKEN or GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)
    try:
        stats, calendar, repos = fetch_github(token, today)
    except Exception as ex:  # noqa: BLE001
        warn(f"GitHub fetch failed, the previous data stays: {ex}")
        return
    old = load("stats.json", {})
    if stats.get("highlight") is None and old.get("highlight"):
        stats["highlight"] = old["highlight"]
    stats["updated"] = today.isoformat()
    save("stats.json", stats)
    save("calendar.json", calendar)
    save("repos.json", repos)
    print("github: ok" + (" (with private contributions)" if os.environ.get("PROFILE_TOKEN") else " (public only)"))


if __name__ == "__main__":
    main()
