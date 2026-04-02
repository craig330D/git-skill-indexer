"""File extraction and chunking — hybrid strategy per file type."""

import ast
import logging
import re
from fnmatch import fnmatch
from pathlib import Path

log = logging.getLogger(__name__)


def chunk_repo(repo_dir: Path, repo_meta: dict, config: dict) -> list[dict]:
    """Extract and chunk all eligible files from a cloned repo."""
    max_size = config.get("max_file_size_kb", 500) * 1024
    include_ext = set(config.get("include_extensions", []))
    exclude_patterns = config.get("exclude_patterns", [])

    chunks = []
    repo_dir = Path(repo_dir)

    for file_path in repo_dir.rglob("*"):
        if not file_path.is_file():
            continue

        rel_path = str(file_path.relative_to(repo_dir))

        # Check exclusions
        if any(fnmatch(rel_path, pat) for pat in exclude_patterns):
            continue

        # Check extension
        suffix = file_path.suffix.lower()
        if suffix not in include_ext:
            continue

        # Check size
        if file_path.stat().st_size > max_size:
            log.debug("Skipping %s (too large)", rel_path)
            continue

        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            log.debug("Could not read %s", rel_path)
            continue

        if not text.strip():
            continue

        base_meta = {
            "repo_name": repo_meta["full_name"],
            "repo_url": repo_meta["html_url"],
            "repo_description": repo_meta.get("description", ""),
            "repo_language": repo_meta.get("language", ""),
            "repo_topics": repo_meta.get("topics", []),
            "file_path": rel_path,
            "file_type": suffix,
        }

        if suffix == ".md":
            chunks.extend(_chunk_markdown(text, base_meta))
        elif suffix == ".py":
            chunks.extend(_chunk_python(text, base_meta))
        elif suffix in {".js", ".ts", ".jsx", ".tsx"}:
            chunks.extend(_chunk_js_ts(text, base_meta))
        elif suffix in {".yaml", ".yml", ".toml", ".json", ".sh", ".mql5", ".mq5"}:
            chunks.extend(_chunk_whole_file(text, base_meta))
        else:
            chunks.extend(_chunk_sliding_window(text, base_meta))

    log.info("Chunked %s: %d chunks from %s", repo_meta["full_name"], len(chunks), repo_dir)
    return chunks


def _chunk_markdown(text: str, meta: dict) -> list[dict]:
    """Split markdown by H1/H2 headings."""
    chunks = []
    sections = re.split(r"(?m)^(#{1,2}\s+.+)$", text)

    current_heading = "intro"
    current_lines = []
    line_offset = 0

    for part in sections:
        if re.match(r"^#{1,2}\s+", part):
            if current_lines:
                content = "".join(current_lines).strip()
                if content:
                    line_count = content.count("\n")
                    chunks.append({
                        **meta,
                        "text": content,
                        "chunk_type": "readme_section",
                        "chunk_name": current_heading,
                        "line_start": line_offset + 1,
                        "line_end": line_offset + line_count + 1,
                    })
                line_offset += "".join(current_lines).count("\n")
            current_heading = part.strip().lstrip("#").strip()
            current_lines = [part + "\n"]
        else:
            current_lines.append(part)

    # Last section
    if current_lines:
        content = "".join(current_lines).strip()
        if content:
            line_count = content.count("\n")
            chunks.append({
                **meta,
                "text": content,
                "chunk_type": "readme_section",
                "chunk_name": current_heading,
                "line_start": line_offset + 1,
                "line_end": line_offset + line_count + 1,
            })

    return chunks


def _chunk_python(text: str, meta: dict) -> list[dict]:
    """AST-based chunking: functions, classes, module docstring."""
    chunks = []
    lines = text.splitlines(keepends=True)

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _chunk_sliding_window(text, meta)

    # Module docstring
    docstring = ast.get_docstring(tree)
    if docstring:
        chunks.append({
            **meta,
            "text": docstring,
            "chunk_type": "module_docstring",
            "chunk_name": meta["file_path"],
            "line_start": 1,
            "line_end": docstring.count("\n") + 1,
        })

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunk_type = "function"
            name = node.name
        elif isinstance(node, ast.ClassDef):
            chunk_type = "class"
            name = node.name
        else:
            continue

        start = node.lineno
        end = node.end_lineno or start
        chunk_text = "".join(lines[start - 1:end])

        if chunk_text.strip():
            chunks.append({
                **meta,
                "text": chunk_text,
                "chunk_type": chunk_type,
                "chunk_name": name,
                "line_start": start,
                "line_end": end,
            })

    if not chunks:
        return _chunk_sliding_window(text, meta)

    return chunks


def _chunk_js_ts(text: str, meta: dict) -> list[dict]:
    """Regex-based function/class extraction for JS/TS."""
    chunks = []
    lines = text.splitlines(keepends=True)

    # Match function declarations, arrow functions, class declarations
    patterns = [
        (r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
        (r"(?:export\s+)?class\s+(\w+)", "class"),
        (r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(", "function"),
    ]

    found_ranges = []
    for pattern, chunk_type in patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1)
            start_pos = match.start()
            line_start = text[:start_pos].count("\n") + 1

            # Find the end by counting braces
            brace_count = 0
            started = False
            line_end = line_start

            for i, line in enumerate(lines[line_start - 1:], start=line_start):
                for ch in line:
                    if ch == "{":
                        brace_count += 1
                        started = True
                    elif ch == "}":
                        brace_count -= 1
                if started and brace_count == 0:
                    line_end = i
                    break

            if not started:
                line_end = min(line_start + 10, len(lines))

            chunk_text = "".join(lines[line_start - 1:line_end])
            if chunk_text.strip():
                found_ranges.append((line_start, line_end))
                chunks.append({
                    **meta,
                    "text": chunk_text,
                    "chunk_type": chunk_type,
                    "chunk_name": name,
                    "line_start": line_start,
                    "line_end": line_end,
                })

    if not chunks:
        return _chunk_sliding_window(text, meta)

    return chunks


def _chunk_whole_file(text: str, meta: dict) -> list[dict]:
    """Treat entire file as a single chunk."""
    line_count = text.count("\n") + 1
    return [{
        **meta,
        "text": text,
        "chunk_type": "config" if meta["file_type"] in {".yaml", ".yml", ".toml", ".json"} else "code_block",
        "chunk_name": meta["file_path"],
        "line_start": 1,
        "line_end": line_count,
    }]


def _chunk_sliding_window(text: str, meta: dict, window: int = 100, overlap: int = 20) -> list[dict]:
    """Sliding window chunking: 100 lines with 20-line overlap."""
    lines = text.splitlines(keepends=True)
    chunks = []
    start = 0

    while start < len(lines):
        end = min(start + window, len(lines))
        chunk_text = "".join(lines[start:end])

        if chunk_text.strip():
            chunks.append({
                **meta,
                "text": chunk_text,
                "chunk_type": "code_block",
                "chunk_name": f"{meta['file_path']}:{start + 1}-{end}",
                "line_start": start + 1,
                "line_end": end,
            })

        start += window - overlap

    return chunks
