"""GitHub API에서 프로필 통계를 수집해 stats.json을 갱신하고 SVG를 재생성한다.

GitHub Actions에서 매일 실행된다. 표준 라이브러리만 사용(의존성 설치 불필요).

토큰: ACCESS_TOKEN(개인 PAT, 비공개 저장소 포함) > GITHUB_TOKEN(공개만) 순으로 사용.
LOC는 저장소별 REST stats/contributors를 합산하며, pushed_at 기준으로
loc_cache.json에 캐싱해 재실행 비용을 줄인다. 현재 토큰으로 보이지 않는
저장소(비공개 등)의 캐시 항목은 지우지 않고 유지한다.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS_PATH = ROOT / "stats.json"
LOC_CACHE_PATH = ROOT / "loc_cache.json"

USER = "soulduse"
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
API = "https://api.github.com"


def request(url: str, data: dict | None = None) -> tuple[int, dict | list | None]:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", USER)
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        return e.code, None


def graphql(query: str, variables: dict | None = None) -> dict:
    status, data = request(f"{API}/graphql", {"query": query, "variables": variables or {}})
    if status != 200 or data is None or "errors" in data:
        raise RuntimeError(f"GraphQL failed: {status} {data}")
    return data["data"]


def fetch_user_and_repos() -> tuple[dict, list[dict]]:
    """사용자 기본 정보 + 소유 저장소 전체(페이지네이션)."""
    repos: list[dict] = []
    cursor = None
    user = None
    while True:
        data = graphql(
            """
            query($login: String!, $cursor: String) {
              user(login: $login) {
                createdAt
                followers { totalCount }
                repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
                  totalCount
                  pageInfo { hasNextPage endCursor }
                  nodes { name isFork isPrivate stargazerCount pushedAt owner { login } }
                }
              }
            }
            """,
            {"login": USER, "cursor": cursor},
        )["user"]
        user = user or data
        page = data["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return user, repos


def fetch_total_commits(created_at: str) -> int:
    """가입 연도부터 올해까지 연도별 컨트리뷰션(공개+비공개)을 합산."""
    start_year = int(created_at[:4])
    this_year = datetime.now(timezone.utc).year
    total = 0
    for year in range(start_year, this_year + 1):
        col = graphql(
            """
            query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  totalCommitContributions
                  restrictedContributionsCount
                }
              }
            }
            """,
            {
                "login": USER,
                "from": f"{year}-01-01T00:00:00Z",
                "to": f"{year}-12-31T23:59:59Z",
            },
        )["user"]["contributionsCollection"]
        total += col["totalCommitContributions"] + col["restrictedContributionsCount"]
    return total


def fetch_loc(repos: list[dict]) -> tuple[int, int]:
    """소유한 비포크 저장소의 본인 작성 LOC(추가/삭제) 합산. pushed_at 캐시 사용."""
    cache: dict = {}
    if LOC_CACHE_PATH.exists():
        cache = json.loads(LOC_CACHE_PATH.read_text())

    targets = [r for r in repos if not r["isFork"]]
    pending = []
    for repo in targets:
        entry = cache.get(repo["name"])
        if entry and entry.get("pushed_at") == repo["pushedAt"]:
            continue
        pending.append(repo)

    for attempt in range(4):
        still = []
        for repo in pending:
            status, data = request(f"{API}/repos/{USER}/{repo['name']}/stats/contributors")
            if status == 202:  # GitHub이 통계 계산 중 — 다음 라운드에 재시도
                still.append(repo)
                continue
            additions = deletions = 0
            if status == 200 and isinstance(data, list):
                for contributor in data:
                    if contributor.get("author", {}).get("login") != USER:
                        continue
                    for week in contributor.get("weeks", []):
                        additions += week.get("a", 0)
                        deletions += week.get("d", 0)
            cache[repo["name"]] = {
                "pushed_at": repo["pushedAt"],
                "additions": additions,
                "deletions": deletions,
            }
        pending = still
        if not pending:
            break
        print(f"waiting for GitHub to compute stats for {len(pending)} repos...")
        time.sleep(10)

    LOC_CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True))
    total_add = sum(e["additions"] for e in cache.values())
    total_del = sum(e["deletions"] for e in cache.values())
    return total_add, total_del


def main() -> None:
    if not TOKEN:
        sys.exit("ACCESS_TOKEN or GITHUB_TOKEN env var required")

    user, repos = fetch_user_and_repos()
    total_commits = fetch_total_commits(user["createdAt"])
    additions, deletions = fetch_loc(repos)

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "created_at": user["createdAt"],
        "followers": user["followers"]["totalCount"],
        "repos_total": len(repos),
        "repos_public": sum(1 for r in repos if not r["isPrivate"]),
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": total_commits,
        "loc_additions": additions,
        "loc_deletions": deletions,
    }
    STATS_PATH.write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))

    import generate_svg

    generate_svg.main()


if __name__ == "__main__":
    main()
