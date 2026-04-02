"""CLI entry point for git-skill-indexer."""

import logging
import sys

import click

from .config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


@click.group()
def main():
    """Git Skill Indexer — semantic search across your starred repos."""
    pass


@main.command()
def sync():
    """Sync starred repos: add new, update changed, remove unstarred."""
    from .sync import run_sync

    config = load_config()
    if not config["github"]["token"]:
        click.echo("Error: GITHUB_PAT environment variable not set", err=True)
        sys.exit(1)

    summary = run_sync(config)
    click.echo(f"Sync complete: +{summary['added']} added, "
               f"~{summary['updated']} updated, "
               f"-{summary['removed']} removed, "
               f"!{summary['errors']} errors")


@main.command()
@click.argument("url")
def index(url: str):
    """Index a specific repo by URL."""
    from .indexer import Indexer

    config = load_config()
    indexer = Indexer(config)
    try:
        count = indexer.index_url(url)
        click.echo(f"Indexed {count} chunks from {url}")
    finally:
        indexer.unload()


@main.command()
@click.argument("search_query")
@click.option("--top-k", "-k", default=5, help="Number of results")
@click.option("--language", "-l", default=None, help="Filter by language")
@click.option("--chunk-type", "-t", default=None, help="Filter by chunk type")
def query(search_query: str, top_k: int, language: str | None, chunk_type: str | None):
    """Search indexed repos with a natural language query."""
    from .embedder import Embedder
    from .store import VectorStore

    config = load_config()
    store = VectorStore(
        host=config["qdrant"]["host"],
        port=config["qdrant"]["port"],
        collection=config["qdrant"]["collection"],
        vector_size=config["qdrant"]["vector_size"],
    )
    emb = Embedder(
        model_name=config["embedding"]["model"],
        device=config["embedding"]["device"],
    )

    try:
        vector = emb.encode([search_query])[0].tolist()
        filters = {}
        if language:
            filters["repo_language"] = language
        if chunk_type:
            filters["chunk_type"] = chunk_type

        results = store.search(vector, top_k=top_k, filters=filters or None)

        if not results:
            click.echo("No results found.")
            return

        for i, r in enumerate(results, 1):
            click.echo(f"\n{'='*60}")
            click.echo(f"[{i}] {r.get('repo_name', '?')} — {r.get('file_path', '?')}")
            click.echo(f"    Score: {r['score']:.4f} | Type: {r.get('chunk_type', '?')} | Name: {r.get('chunk_name', '?')}")
            click.echo(f"    Lines: {r.get('line_start', '?')}-{r.get('line_end', '?')}")
            text = r.get("text", "")
            if len(text) > 300:
                text = text[:300] + "..."
            click.echo(f"    {text}")
    finally:
        emb.unload()


@main.command()
def repos():
    """List all indexed repos."""
    from .store import VectorStore

    config = load_config()
    store = VectorStore(
        host=config["qdrant"]["host"],
        port=config["qdrant"]["port"],
        collection=config["qdrant"]["collection"],
        vector_size=config["qdrant"]["vector_size"],
    )
    indexed = store.get_indexed_repos()
    if not indexed:
        click.echo("No repos indexed yet.")
        return
    click.echo(f"{len(indexed)} indexed repos:")
    for name in indexed:
        click.echo(f"  {name}")


@main.command()
@click.argument("repo_name")
def remove(repo_name: str):
    """Remove a repo from the index by owner/name."""
    from .store import VectorStore

    config = load_config()
    store = VectorStore(
        host=config["qdrant"]["host"],
        port=config["qdrant"]["port"],
        collection=config["qdrant"]["collection"],
        vector_size=config["qdrant"]["vector_size"],
    )
    store.delete_repo(repo_name)
    click.echo(f"Removed {repo_name} from index.")


@main.command()
def stats():
    """Show collection statistics."""
    from .store import VectorStore

    config = load_config()
    store = VectorStore(
        host=config["qdrant"]["host"],
        port=config["qdrant"]["port"],
        collection=config["qdrant"]["collection"],
        vector_size=config["qdrant"]["vector_size"],
    )
    s = store.get_stats()
    click.echo(f"Total chunks: {s['total_chunks']}")
    click.echo(f"Total repos:  {s['total_repos']}")
    click.echo(f"Vector size:  {s['vector_size']}")
    click.echo(f"Status:       {s['status']}")


@main.command()
def reindex():
    """Force full re-index of all starred repos."""
    from .sync import run_sync, _load_state, _save_state

    config = load_config()
    if not config["github"]["token"]:
        click.echo("Error: GITHUB_PAT environment variable not set", err=True)
        sys.exit(1)

    # Clear state to force all repos to be re-indexed
    _save_state({})
    click.echo("State cleared. Running full sync...")
    summary = run_sync(config)
    click.echo(f"Reindex complete: +{summary['added']} added, "
               f"~{summary['updated']} updated, "
               f"-{summary['removed']} removed, "
               f"!{summary['errors']} errors")


if __name__ == "__main__":
    main()
