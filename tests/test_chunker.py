"""Tests for chunker module."""

from src.chunker import chunk_repo
from pathlib import Path
import tempfile
import os


def _make_repo(tmp_dir: str, files: dict[str, str]) -> Path:
    """Create a temp directory with files for testing."""
    repo_dir = Path(tmp_dir) / "test_repo"
    for rel_path, content in files.items():
        full_path = repo_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
    return repo_dir


REPO_META = {
    "full_name": "test/repo",
    "html_url": "https://github.com/test/repo",
    "description": "Test repo",
    "language": "Python",
    "topics": ["test"],
}

CONFIG = {
    "max_file_size_kb": 500,
    "include_extensions": [".py", ".md", ".json", ".yaml"],
    "exclude_patterns": ["node_modules/**", ".git/**", "__pycache__/**"],
}


def test_markdown_chunking():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp, {
            "README.md": "# Intro\nHello world\n\n## Setup\nDo this\n\n## Usage\nUse it\n"
        })
        chunks = chunk_repo(repo, REPO_META, CONFIG)
        assert len(chunks) >= 3
        assert all(c["chunk_type"] == "readme_section" for c in chunks)
        names = [c["chunk_name"] for c in chunks]
        assert "Intro" in names
        assert "Setup" in names
        assert "Usage" in names


def test_python_chunking():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp, {
            "main.py": '"""Module doc."""\n\ndef foo():\n    return 1\n\nclass Bar:\n    pass\n'
        })
        chunks = chunk_repo(repo, REPO_META, CONFIG)
        types = {c["chunk_type"] for c in chunks}
        assert "function" in types
        assert "class" in types


def test_json_whole_file():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp, {
            "config.json": '{"key": "value"}\n'
        })
        chunks = chunk_repo(repo, REPO_META, CONFIG)
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "config"


def test_excludes_node_modules():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp, {
            "node_modules/pkg/index.py": "x = 1\n",
            "src/main.py": "y = 2\n",
        })
        chunks = chunk_repo(repo, REPO_META, CONFIG)
        paths = [c["file_path"] for c in chunks]
        assert not any("node_modules" in p for p in paths)


def test_skips_large_files():
    with tempfile.TemporaryDirectory() as tmp:
        large_content = "x" * (600 * 1024)  # 600KB > 500KB limit
        repo = _make_repo(tmp, {"big.py": large_content})
        chunks = chunk_repo(repo, REPO_META, CONFIG)
        assert len(chunks) == 0


def test_skips_unlisted_extensions():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp, {"style.css": "body { color: red; }"})
        chunks = chunk_repo(repo, REPO_META, CONFIG)
        assert len(chunks) == 0
