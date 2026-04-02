"""Diff logic: new stars, updated repos, unstarred — nightly sync."""

import json
import logging
from datetime import datetime, timezone

from .config import get_state_path
from .github_client import GitHubClient
from .indexer import Indexer

log = logging.getLogger(__name__)


def _load_state() -> dict:
    path = get_state_path()
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_state(state: dict):
    path = get_state_path()
    path.write_text(json.dumps(state, indent=2))


def run_sync(config: dict) -> dict:
    """Run full sync: fetch stars, diff against index, process changes.

    Returns summary dict: {added, updated, removed, errors}.
    """
    gh = GitHubClient(
        username=config["github"]["username"],
        token=config["github"]["token"],
        exclude_repos=config["github"].get("exclude_repos"),
        exclude_owners=config["github"].get("exclude_owners"),
        include_private=config["github"].get("include_private", True),
    )
    indexer = Indexer(config)
    state = _load_state()

    starred = gh.get_starred_repos()
    starred_names = {r["full_name"] for r in starred}
    starred_map = {r["full_name"]: r for r in starred}

    indexed_repos = set(indexer.store.get_indexed_repos())

    new_repos = starred_names - indexed_repos
    removed_repos = indexed_repos - starred_names
    existing_repos = starred_names & indexed_repos

    # Check for updates in existing repos
    updated_repos = set()
    for name in existing_repos:
        repo = starred_map[name]
        pushed_at = repo.get("pushed_at", "")
        last_indexed = state.get(name, {}).get("last_indexed_at", "")
        if pushed_at and pushed_at > last_indexed:
            updated_repos.add(name)

    summary = {"added": 0, "updated": 0, "removed": 0, "errors": 0}
    now = datetime.now(timezone.utc).isoformat()

    # Process new repos
    for name in sorted(new_repos):
        try:
            count = indexer.index_repo(starred_map[name])
            state[name] = {"last_indexed_at": now, "pushed_at": starred_map[name].get("pushed_at", "")}
            summary["added"] += 1
            log.info("Added %s (%d chunks)", name, count)
        except Exception:
            summary["errors"] += 1
            log.exception("Failed to index %s", name)

    # Process updated repos
    for name in sorted(updated_repos):
        try:
            count = indexer.index_repo(starred_map[name], force=True)
            state[name] = {"last_indexed_at": now, "pushed_at": starred_map[name].get("pushed_at", "")}
            summary["updated"] += 1
            log.info("Updated %s (%d chunks)", name, count)
        except Exception:
            summary["errors"] += 1
            log.exception("Failed to update %s", name)

    # Process removed repos
    for name in sorted(removed_repos):
        try:
            indexer.remove_repo(name)
            state.pop(name, None)
            summary["removed"] += 1
            log.info("Removed %s", name)
        except Exception:
            summary["errors"] += 1
            log.exception("Failed to remove %s", name)

    _save_state(state)
    indexer.unload()

    log.info("Sync complete: added=%d, updated=%d, removed=%d, errors=%d",
             summary["added"], summary["updated"], summary["removed"], summary["errors"])
    return summary
