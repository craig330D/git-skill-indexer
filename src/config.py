"""Configuration loader — YAML file + environment variable overrides."""

import os
from pathlib import Path

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
STATE_DIR = Path.home() / ".git-skill-indexer"


def load_config(path: Path | None = None) -> dict:
    """Load config from YAML file, resolve env vars for secrets."""
    path = path or DEFAULT_CONFIG_PATH
    with open(path) as f:
        cfg = yaml.safe_load(f)

    # Resolve GitHub PAT from env var
    token_env = cfg.get("github", {}).get("token_env", "GITHUB_PAT")
    cfg["github"]["token"] = os.environ.get(token_env, "")

    # Ensure defaults
    cfg.setdefault("embedding", {})
    cfg["embedding"].setdefault("model", "all-MiniLM-L6-v2")
    cfg["embedding"].setdefault("device", "cpu")
    cfg["embedding"].setdefault("batch_size", 64)

    cfg.setdefault("qdrant", {})
    cfg["qdrant"].setdefault("host", "localhost")
    cfg["qdrant"].setdefault("port", 6333)
    cfg["qdrant"].setdefault("collection", "git-skills")
    cfg["qdrant"].setdefault("vector_size", 384)

    cfg.setdefault("indexer", {})
    cfg["indexer"].setdefault("clone_dir", "/tmp/git-skill-indexer/repos")
    cfg["indexer"].setdefault("max_file_size_kb", 500)

    cfg.setdefault("server", {})
    cfg["server"].setdefault("host", "0.0.0.0")
    cfg["server"].setdefault("port", 8420)
    cfg["server"].setdefault("mcp_enabled", True)

    return cfg


def get_state_path() -> Path:
    """Return path to state.json, creating directory if needed."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "state.json"
