"""Dynamic routing from project intent to independently registered modules."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Iterable

from .models import Capability
from .modules.contract import ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry, ModuleRegistryError


PREFERRED_DOMAIN_ORDER = ("evidence", "omics", "molecular_design", "imaging", "clinical", "wetlab", "publication")
SERIAL_DOMAINS = frozenset({"evidence", "publication"})
_DEFAULT_REGISTRY = ModuleRegistry.discover(BUILTIN_ROOT)
_ASCII_STOP = frozenset({"analyze", "analysis", "assess", "data", "result", "results", "run", "scientific", "summary", "test", "tool"})
_CJK_STOP = frozenset({"分析", "数据", "结果", "进行", "检查", "评估", "科研", "汇总", "工具"})


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower().strip()


def _features(value: str) -> set[str]:
    normalized = _normalize(value)
    features = {
        token
        for token in re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", normalized)
        if len(token) > 1 and token not in _ASCII_STOP
    }
    for run in re.findall(r"[\u3400-\u9fff]+", normalized):
        for width in (2, 3, 4):
            features.update(run[index : index + width] for index in range(max(0, len(run) - width + 1)))
    return {feature for feature in features if feature not in _CJK_STOP}


def _phrase_matches(query: str, phrases: Iterable[str]) -> list[str]:
    normalized_query = _normalize(query)
    return [phrase for phrase in phrases if _normalize(phrase) in normalized_query]


def _score_module(module: ModuleManifest, query: str) -> tuple[float, list[str]]:
    query_features = _features(query)
    exact_intents = _phrase_matches(query, module.intents)
    exact_questions = _phrase_matches(query, module.questions)
    title_exact = _phrase_matches(query, (module.title,))
    intent_overlap = query_features & set().union(*(_features(value) for value in module.intents))
    question_overlap = query_features & set().union(*(_features(value) for value in module.questions))
    title_overlap = query_features & _features(module.title)
    description_overlap = query_features & _features(module.description)
    artifact_overlap = query_features & {
        feature
        for port in (*module.input_artifacts, *module.output_artifacts)
        for feature in _features(port.artifact_type.replace("_", " "))
    }
    score = 0.0
    score += 20.0 * len(exact_intents)
    score += 12.0 * len(exact_questions)
    score += 14.0 * len(title_exact)
    score += 3.5 * len(intent_overlap)
    score += 2.5 * len(question_overlap)
    score += 3.0 * len(title_overlap)
    score += 0.75 * len(description_overlap)
    score += 1.5 * len(artifact_overlap)
    if module.access == "offline":
        score += 0.25
    reasons = []
    if exact_intents:
        reasons.append(f"exact intent: {exact_intents[0]}")
    if title_exact:
        reasons.append("title matches the request")
    concepts = sorted(intent_overlap | question_overlap | title_overlap | artifact_overlap, key=lambda value: (-len(value), value))
    if concepts:
        reasons.append(f"matched concepts: {', '.join(concepts[:5])}")
    if not reasons and description_overlap:
        reasons.append(f"description concepts: {', '.join(sorted(description_overlap)[:5])}")
    return score, reasons


def _domain_order(domains: Iterable[str]) -> list[str]:
    values = set(domains)
    ordered = [domain for domain in PREFERRED_DOMAIN_ORDER if domain in values]
    ordered.extend(sorted(values - set(PREFERRED_DOMAIN_ORDER)))
    return ordered


def infer_workflows(query: str, *, registry: ModuleRegistry | None = None) -> list[str]:
    active = registry or _DEFAULT_REGISTRY
    domain_scores: dict[str, float] = defaultdict(float)
    for module in active.all():
        score, reasons = _score_module(module, query)
        if reasons:
            for domain in module.domains:
                domain_scores[domain] = max(domain_scores[domain], score)
    matched = {domain for domain, score in domain_scores.items() if score >= 5.0}
    if matched:
        return _domain_order(matched)
    fallback = [module for module in active.all() if module.module_type == "data_source"]
    if fallback:
        return _domain_order(fallback[0].domains)
    return _domain_order(active.all()[0].domains)


def score_capability(
    capability: Capability | ModuleManifest,
    query: str,
    workflows: Iterable[str] = (),
    *,
    registry: ModuleRegistry | None = None,
) -> float:
    active = registry or _DEFAULT_REGISTRY
    if isinstance(capability, ModuleManifest):
        module = capability
    else:
        try:
            module = active.get(capability.id)
        except ModuleRegistryError:
            text = f"{capability.id} {capability.title} {capability.description}"
            return float(len(_features(query) & _features(text)))
    score, _reasons = _score_module(module, query)
    if set(module.domains) & set(workflows):
        score += 2.0
    return score


def route(query: str, *, per_workflow: int = 3, registry: ModuleRegistry | None = None) -> dict[str, Any]:
    if not query.strip() or not 1 <= per_workflow <= 10:
        raise ValueError("query must be nonempty and per_workflow must be 1..10")
    active = registry or _DEFAULT_REGISTRY
    workflows = infer_workflows(query, registry=active)
    grouped: dict[str, list[tuple[float, ModuleManifest, list[str]]]] = defaultdict(list)
    for module in active.all():
        score, reasons = _score_module(module, query)
        for domain in module.domains:
            if domain in workflows:
                grouped[domain].append((score + 2.0, module, reasons or [f"available in matched domain: {domain}"]))
    candidates = {}
    for workflow in workflows:
        ranked = sorted(grouped[workflow], key=lambda item: (-item[0], item[1].id))
        candidates[workflow] = [
            {
                "id": module.id,
                "title": module.title,
                "score": round(score, 3),
                "access": module.access,
                "mutability": module.mutability,
                "maturity": module.maturity,
                "selection_reasons": reasons,
            }
            for score, module, reasons in ranked[:per_workflow]
        ]
    parallel_requested = any(term in _normalize(query) for term in ("parallel", "并行", "同时"))
    if len(workflows) == 1:
        plan_type = "single"
    elif parallel_requested and not (SERIAL_DOMAINS & set(workflows)):
        plan_type = "parallel"
    elif parallel_requested:
        plan_type = "mixed"
    else:
        plan_type = "serial"
    steps = []
    for workflow in workflows:
        mode = "parallel" if plan_type in {"parallel", "mixed"} and workflow not in SERIAL_DOMAINS else "serial"
        steps.append({"workflow": workflow, "mode": mode, "candidates": candidates[workflow]})
    return {"objective": query, "matched_workflows": workflows, "plan_type": plan_type, "steps": steps}
