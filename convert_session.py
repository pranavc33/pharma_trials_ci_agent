#!/usr/bin/env python3
"""Convert Codex JSONL session to readable markdown."""

import json
import sys
from pathlib import Path


def extract_text(content_items):
    """Extract text from a list of content items (Codex uses various formats)."""
    if isinstance(content_items, str):
        return content_items
    if not isinstance(content_items, list):
        return str(content_items)
    parts = []
    for item in content_items:
        if isinstance(item, dict):
            text = item.get("text") or item.get("content") or ""
            parts.append(text)
        else:
            parts.append(str(item))
    return "\n".join(p for p in parts if p)


def main(input_path, output_path):
    events = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    output_lines = []
    session_meta = next((e for e in events if e.get("type") == "session_meta"), None)
    if session_meta:
        meta = session_meta.get("payload", {})
        git = meta.get("git", {})
        output_lines.append("# Codex Session Log")
        output_lines.append("")
        output_lines.append(f"**Session ID:** {meta.get('session_id', 'unknown')}")
        output_lines.append(f"**Started:** {meta.get('timestamp', 'unknown')}")
        output_lines.append(f"**Working directory:** {meta.get('cwd', 'unknown')}")
        output_lines.append(f"**Codex version:** {meta.get('cli_version', 'unknown')}")
        if git:
            output_lines.append(f"**Repository:** {git.get('repository_url', 'unknown')}")
            output_lines.append(f"**Branch:** {git.get('branch', 'unknown')}")
        output_lines.append("")
        output_lines.append("---")
        output_lines.append("")

    for event in events:
        if event.get("type") != "response_item":
            continue
        payload = event.get("payload", {})
        payload_type = payload.get("type", "")

        if payload_type == "message":
            role = payload.get("role", "unknown")
            content = extract_text(payload.get("content", []))
            if not content.strip():
                continue
            if role == "developer" or role == "system":
                continue  # skip system prompts and permissions boilerplate
            if role == "user":
                output_lines.append("## User")
            elif role == "assistant":
                output_lines.append("## Assistant")
            else:
                output_lines.append(f"## {role.title()}")
            output_lines.append("")
            output_lines.append(content)
            output_lines.append("")

        elif payload_type == "function_call":
            name = payload.get("name", "unknown_tool")
            args = payload.get("arguments", "")
            if isinstance(args, str):
                try:
                    args_obj = json.loads(args)
                    args = json.dumps(args_obj, indent=2)
                except (json.JSONDecodeError, TypeError):
                    pass
            output_lines.append(f"### Tool call: `{name}`")
            output_lines.append("")
            output_lines.append("```")
            output_lines.append(str(args)[:2000])  # truncate huge args
            output_lines.append("```")
            output_lines.append("")

        elif payload_type == "function_call_output":
            output = payload.get("output", "")
            if isinstance(output, dict):
                output = output.get("content", output.get("output", str(output)))
            output_text = str(output)[:2000]  # truncate huge outputs
            output_lines.append("### Tool output")
            output_lines.append("")
            output_lines.append("```")
            output_lines.append(output_text)
            output_lines.append("```")
            output_lines.append("")

    Path(output_path).write_text("\n".join(output_lines), encoding="utf-8")
    print(f"Converted {len([e for e in events if e.get('type') == 'response_item'])} response items")
    print(f"Output written to {output_path}")
    print(f"Output file size: {Path(output_path).stat().st_size:,} bytes")


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "codex_session_main.jsonl"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "codex_session.md"
    main(input_file, output_file)
