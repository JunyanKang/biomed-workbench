"""Aggregate per-file understanding into architecture-driving domain signals."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from .assimilation import FileRecord


def _words(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return " ".join(part for part in re.split(r"[_\W]+", value.lower()) if part)


def synthesize_learning(records: Iterable[FileRecord]) -> dict[str, Any]:
    records = list(records)
    groups: dict[str, list[FileRecord]] = defaultdict(list)
    for record in records:
        groups[record.capability_cluster].append(record)
    clusters: dict[str, Any] = {}
    for cluster, items in sorted(groups.items()):
        dependencies: Counter[str] = Counter()
        operations: Counter[str] = Counter()
        rule_sections: Counter[str] = Counter()
        roles = Counter(str(item.understanding.get("role", "unknown")) for item in items)
        formats = Counter(item.format for item in items)
        dispositions = Counter(item.disposition for item in items)
        for item in items:
            semantic = item.semantic
            for dependency in (*semantic.get("imports", ()), *semantic.get("code_imports", ())):
                if isinstance(dependency, str) and dependency:
                    dependencies[dependency] += 1
            for symbol in (*semantic.get("public_symbols", ()), *semantic.get("code_symbols", ()), *semantic.get("exports", ())):
                if isinstance(symbol, str) and symbol:
                    operations[_words(symbol)] += 1
            for heading in (*semantic.get("headings", ()), *semantic.get("markdown_headings", ())):
                if isinstance(heading, dict) and heading.get("text"):
                    rule_sections[_words(str(heading["text"]))] += 1
        implications = []
        executable_count = roles.get("executable_logic", 0)
        workflow_count = roles.get("assistant_workflow", 0)
        verification_count = roles.get("verification", 0)
        if executable_count:
            implications.append(f"Redesign {executable_count} executable files as validated source-neutral capability contracts.")
        if workflow_count:
            implications.append(f"Consolidate {workflow_count} workflow files behind the single Codex skill entrypoint.")
        if verification_count:
            implications.append(f"Translate {verification_count} verification files into behavioral and end-to-end tests.")
        if dispositions.get("generated_runtime", 0):
            implications.append("Use generated runtime files only for dependency and readiness modeling.")
        clusters[cluster] = {
            "file_count": len(items),
            "role_counts": dict(sorted(roles.items())),
            "format_counts": dict(sorted(formats.items())),
            "disposition_counts": dict(sorted(dispositions.items())),
            "public_symbol_count": sum(int(item.understanding.get("public_symbol_count", 0)) for item in items),
            "top_dependencies": [[name, count] for name, count in dependencies.most_common(30)],
            "operation_signals": [[name, count] for name, count in operations.most_common(50)],
            "rule_signals": [[name, count] for name, count in rule_sections.most_common(30)],
            "design_implications": implications,
        }
    return {
        "schema_version": 1,
        "learned_file_count": len(records),
        "source_counts": dict(sorted(Counter(record.source for record in records).items())),
        "clusters": clusters,
    }
