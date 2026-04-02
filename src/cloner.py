"""Shallow clone and cleanup logic."""

import logging
import shutil
from pathlib import Path

import git

log = logging.getLogger(__name__)


def shallow_clone(clone_url: str, target_dir: Path) -> Path:
    """Shallow clone a repo, remove .git dir to save space."""
    target_dir = Path(target_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)

    log.info("Cloning %s → %s", clone_url, target_dir)
    git.Repo.clone_from(clone_url, str(target_dir), depth=1, single_branch=True)

    # Remove .git to save space
    git_dir = target_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)

    return target_dir


def cleanup_clone(target_dir: Path):
    """Remove cloned repo directory."""
    target_dir = Path(target_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)
        log.debug("Cleaned up %s", target_dir)
