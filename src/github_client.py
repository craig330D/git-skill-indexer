"""GitHub API client — fetch starred repos with pagination and rate limiting."""

import logging
import time

import requests

log = logging.getLogger(__name__)


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, username: str, token: str, exclude_repos: list[str] | None = None,
                 exclude_owners: list[str] | None = None, include_private: bool = True):
        self.username = username
        self.token = token
        self.exclude_repos = set(exclude_repos or [])
        self.exclude_owners = set(exclude_owners or [])
        self.include_private = include_private
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"token {token}"
        self.session.headers["Accept"] = "application/vnd.github.v3+json"

    def _check_rate_limit(self, response: requests.Response):
        remaining = int(response.headers.get("X-RateLimit-Remaining", 100))
        if remaining < 10:
            reset_at = int(response.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_at - int(time.time()), 1)
            log.warning("Rate limit low (%d remaining), sleeping %ds", remaining, wait)
            time.sleep(wait)

    def get_starred_repos(self) -> list[dict]:
        """Fetch all starred repos with pagination."""
        repos = []
        url = f"{self.BASE_URL}/users/{self.username}/starred"
        params = {"per_page": 100, "page": 1}

        while url:
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            self._check_rate_limit(resp)

            for repo in resp.json():
                full_name = repo["full_name"]
                owner = full_name.split("/")[0]

                if full_name in self.exclude_repos:
                    continue
                if owner in self.exclude_owners:
                    continue
                if repo["private"] and not self.include_private:
                    continue

                repos.append({
                    "full_name": full_name,
                    "html_url": repo["html_url"],
                    "clone_url": repo["clone_url"],
                    "description": repo.get("description") or "",
                    "language": repo.get("language") or "",
                    "topics": repo.get("topics", []),
                    "stargazers_count": repo.get("stargazers_count", 0),
                    "updated_at": repo.get("updated_at", ""),
                    "pushed_at": repo.get("pushed_at", ""),
                })

            # Follow pagination
            link = resp.headers.get("Link", "")
            url = None
            params = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    break

        log.info("Fetched %d starred repos (after exclusions)", len(repos))
        return repos
