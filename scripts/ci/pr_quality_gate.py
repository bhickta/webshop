#!/usr/bin/env python3
"""Safe, deterministic checks for files changed by a pull request."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = os.environ["PR_BASE_SHA"]
HEAD_SHA = os.environ["PR_HEAD_SHA"]


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		["git", *args],
		cwd=ROOT,
		check=check,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
	)


def changed_files() -> list[Path]:
	result = git("diff", "--name-only", "--diff-filter=ACMR", BASE_SHA, HEAD_SHA)
	return [ROOT / line for line in result.stdout.splitlines() if line]


def add_summary(lines: list[str]) -> None:
	path = os.environ.get("GITHUB_STEP_SUMMARY")
	if not path:
		return
	with Path(path).open("a", encoding="utf-8") as handle:
		handle.write("\n".join(lines) + "\n")


def find_duplicate_functions(tree: ast.Module) -> list[str]:
	duplicates: list[str] = []
	scopes: list[tuple[str, list[ast.stmt]]] = [("module", tree.body)]
	scopes.extend(
		(f"class {node.name}", node.body)
		for node in ast.walk(tree)
		if isinstance(node, ast.ClassDef)
	)

	for scope_name, body in scopes:
		seen: dict[str, int] = {}
		for node in body:
			if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				continue
			if node.name in seen:
				duplicates.append(
					f"{scope_name} function {node.name!r} at lines "
					f"{seen[node.name]} and {node.lineno}"
				)
			else:
				seen[node.name] = node.lineno

	return duplicates


def main() -> int:
	errors: list[str] = []
	warnings: list[str] = []
	files = changed_files()
	relative_files = [path.relative_to(ROOT).as_posix() for path in files]

	diff_check = git("diff", "--check", BASE_SHA, HEAD_SHA, check=False)
	if diff_check.returncode:
		errors.append("Whitespace/conflict-marker check failed:\n" + diff_check.stdout.strip())

	for path, relative in zip(files, relative_files, strict=True):
		if not path.is_file():
			continue
		try:
			if path.suffix == ".py":
				tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
				for duplicate in find_duplicate_functions(tree):
					errors.append(f"{relative}: duplicate {duplicate}")
			elif path.suffix == ".json":
				data = json.loads(path.read_text(encoding="utf-8"))
				if data.get("doctype") == "DocType" and path.parent.parent.name == "doctype":
					actual_name = re.sub(r"[^a-z0-9]+", "_", data.get("name", "").lower()).strip("_")
					if actual_name != path.parent.name:
						errors.append(
							f"{relative}: DocType name {data.get('name')!r} does not match "
							f"directory {path.parent.name!r}"
						)
			elif path.suffix in {".js", ".mjs", ".cjs"}:
				check = subprocess.run(
					["node", "--check", str(path)],
					cwd=ROOT,
					text=True,
					stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT,
				)
				if check.returncode:
					errors.append(f"{relative}: JavaScript syntax check failed\n{check.stdout.strip()}")
			elif path.suffix == ".sh":
				check = subprocess.run(
					["bash", "-n", str(path)],
					cwd=ROOT,
					text=True,
					stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT,
				)
				if check.returncode:
					errors.append(f"{relative}: shell syntax check failed\n{check.stdout.strip()}")
		except (SyntaxError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
			errors.append(f"{relative}: {exc}")

	code_suffixes = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".vue"}
	code_changed = any(path.suffix in code_suffixes for path in files)
	test_changed = any("test" in path.name.lower() or "test" in path.parts for path in files)
	if code_changed and not test_changed:
		warnings.append("Functional code changed without a changed test file; require manual test evidence in the PR.")

	changed_lines = git("diff", "--numstat", BASE_SHA, HEAD_SHA).stdout.splitlines()
	line_total = 0
	for line in changed_lines:
		added, deleted, *_ = line.split("\t")
		if added.isdigit():
			line_total += int(added)
		if deleted.isdigit():
			line_total += int(deleted)
	if len(files) > 40 or line_total > 1500:
		warnings.append(
			f"Large PR ({len(files)} files, {line_total} changed lines); split it or document why one review is safe."
		)

	high_risk_fragments = (
		"hooks.py",
		"/patches/",
		"permission",
		"account",
		"stock",
		"webhook",
		"integration",
	)
	high_risk = [
		name for name in relative_files if any(fragment in name.lower() for fragment in high_risk_fragments)
	]
	if high_risk:
		warnings.append("High-risk paths require explicit regression and rollback evidence: " + ", ".join(high_risk[:12]))

	add_summary(
		[
			"## PR quality gate",
			f"- Changed files checked: {len(files)}",
			f"- Changed lines: {line_total}",
			f"- Errors: {len(errors)}",
			f"- Review warnings: {len(warnings)}",
			*(["", "### Warnings", *[f"- {warning}" for warning in warnings]] if warnings else []),
		]
	)

	for warning in warnings:
		print(f"::warning::{warning}")
	for error in errors:
		print(f"::error::{error}")

	if errors:
		print(f"PR quality gate failed with {len(errors)} error(s).")
		return 1
	print(f"PR quality gate passed for {len(files)} changed file(s), with {len(warnings)} review warning(s).")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
