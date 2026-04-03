"""Local MCP stdio bridge to the remote git-skill-indexer API on Proxmox."""

import json
import sys
import requests

API_BASE = "http://172.18.2.1:8420"


def handle_request(req: dict) -> dict:
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "skill-search", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # No response needed for notifications

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "skill_search",
                        "description": "Search indexed GitHub repositories for relevant code patterns, agents, skills, and tools. Searches across 17+ starred repos with 300K+ code chunks.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Natural language search query"},
                                "top_k": {"type": "integer", "default": 5, "description": "Number of results to return"},
                                "language": {"type": "string", "description": "Filter by programming language (e.g. Python, JavaScript)"},
                                "chunk_type": {"type": "string", "description": "Filter by chunk type: function, class, readme_section, config, code_block"},
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "skill_repos",
                        "description": "List all indexed repositories in the skill search index",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "skill_stats",
                        "description": "Get statistics about the skill search index (total chunks, repos, etc.)",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                ]
            },
        }

    if method == "tools/call":
        tool_name = req.get("params", {}).get("name", "")
        args = req.get("params", {}).get("arguments", {})

        try:
            if tool_name == "skill_search":
                resp = requests.post(
                    f"{API_BASE}/mcp/tools/skill_search",
                    json=args,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])

                # Format results as readable text
                lines = []
                for i, r in enumerate(results, 1):
                    lines.append(f"[{i}] {r.get('repo', '?')} — {r.get('file', '?')}")
                    lines.append(f"    Score: {r.get('score', 0):.4f} | Type: {r.get('type', '?')} | Name: {r.get('name', '?')}")
                    text = r.get("text", "")
                    if len(text) > 500:
                        text = text[:500] + "..."
                    lines.append(f"    {text}")
                    lines.append("")

                content = "\n".join(lines) if lines else "No results found."

            elif tool_name == "skill_repos":
                resp = requests.get(f"{API_BASE}/repos", timeout=10)
                resp.raise_for_status()
                data = resp.json()
                repos = data.get("repos", [])
                content = f"{len(repos)} indexed repos:\n" + "\n".join(f"  - {r}" for r in repos)

            elif tool_name == "skill_stats":
                resp = requests.get(f"{API_BASE}/stats", timeout=10)
                resp.raise_for_status()
                data = resp.json()
                content = json.dumps(data, indent=2)

            else:
                content = f"Unknown tool: {tool_name}"

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": content}],
                },
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            pass


if __name__ == "__main__":
    main()
