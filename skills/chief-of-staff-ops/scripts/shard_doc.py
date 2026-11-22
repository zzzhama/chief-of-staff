#!/usr/bin/env python3
"""Troceador de documentos estilo BMAD shard-doc: divide Markdown largo por secciones '## '."""
import os
import re
import sys

def shard_markdown(file_path: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    sections = re.split(r"(?m)(?=^##\s+)", content)
    index_lines = [f"# Index for {os.path.basename(file_path)}\n"]

    for i, sec in enumerate(sections):
        lines = sec.strip().splitlines()
        header = lines[0] if lines else f"Section {i}"
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", header.replace("#", "").strip().lower())[:30]
        shard_filename = f"{i:02d}_{safe_name}.md"
        with open(os.path.join(out_dir, shard_filename), "w", encoding="utf-8") as sf:
            sf.write(sec)
        index_lines.append(f"- [{header}]({shard_filename}) ({len(lines)} lines)")

    with open(os.path.join(out_dir, "index.md"), "w", encoding="utf-8") as inf:
        inf.write("\n".join(index_lines) + "\n")
    print(f"Sharded into {len(sections)} files in {out_dir}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: shard_doc.py <doc.md> <out_dir>")
        sys.exit(1)
    shard_markdown(sys.argv[1], sys.argv[2])
