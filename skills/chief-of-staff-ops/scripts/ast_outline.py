#!/usr/bin/env python3
"""Extractor de esqueletos AST estilo Aider RepoMap (<30 líneas) con números de línea exactos."""
import ast
import sys

def outline(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    print(f"=== Skeleton for {path} ===")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            print(f"[L{node.lineno}-L{end}] class {node.name}:")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    iend = getattr(item, "end_lineno", item.lineno)
                    args = [a.arg for a in item.args.args]
                    print(f"  [L{item.lineno}-L{iend}] def {item.name}({', '.join(args)})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            args = [a.arg for a in node.args.args]
            print(f"[L{node.lineno}-L{end}] def {node.name}({', '.join(args)})")

if __name__ == "__main__":
    for p in sys.argv[1:]:
        outline(p)
