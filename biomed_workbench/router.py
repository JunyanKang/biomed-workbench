"""Dynamic routing from project intent to independently registered modules."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Iterable

from .models import Capability
from .modules.contract import ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry, ModuleRegistryError


PREFERRED_DOMAIN_ORDER = ("evidence", "omics", "molecular_design", "imaging", "clinical", "wetlab", "publication")
SERIAL_DOMAINS = frozenset({"evidence", "publication"})
_DEFAULT_REGISTRY = ModuleRegistry.discover(BUILTIN_ROOT)
_ASCII_STOP = frozenset(
    {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "then", "to", "with",
        "analyze", "analysis", "assess", "data", "result", "results", "run", "scientific", "summary", "test", "tool",
    }
)
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


def _matched_features(module: ModuleManifest, query: str) -> set[str]:
    query_features = _features(query)
    searchable = (
        *module.intents,
        *module.questions,
        module.title,
        module.description,
        *(port.artifact_type.replace("_", " ") for port in (*module.input_artifacts, *module.output_artifacts)),
    )
    return query_features & set().union(*(_features(value) for value in searchable))


def _select_ranked_modules(
    ranked: list[tuple[float, ModuleManifest, list[str]]], query: str
) -> list[str]:
    """Select a compact, nonredundant module set without module-specific rules."""
    if not ranked:
        return []
    normalized = _normalize(query)
    multi_intent = any(token in normalized for token in (" and ", " then ", "同时", "并行", "以及", "并且", "然后", "最后", "和"))
    exact = [item for item in ranked if any(reason.startswith("exact intent:") or reason == "title matches the request" for reason in item[2])]
    selected: list[tuple[float, ModuleManifest, list[str]]] = exact[:] if exact else [ranked[0]]
    dominant_exact = [
        item
        for item in exact
        if any(
            len(_normalize(phrase)) / len(normalized) >= 0.75
            for phrase in (*item[1].intents, *item[1].questions, item[1].title)
            if _normalize(phrase) in normalized
        )
    ]
    if dominant_exact:
        return [item[1].id for item in dominant_exact]
    if exact and not multi_intent:
        return [item[1].id for item in selected]

    top_score = ranked[0][0]
    threshold = max(5.0, top_score * 0.25)
    covered = set().union(*(_matched_features(item[1], query) for item in selected))
    for item in ranked:
        score, module, reasons = item
        selected_ids = {chosen[1].id for chosen in selected}
        if module.id in selected_ids or score < threshold or len(selected) >= 4:
            continue
        if not reasons or all(reason.startswith("available in matched workflow") for reason in reasons):
            continue
        if any(module.id in chosen[1].alternatives or chosen[1].id in module.alternatives for chosen in selected):
            continue
        features = _matched_features(module, query)
        if not features - covered:
            continue
        selected.append(item)
        covered.update(features)
    return [item[1].id for item in selected]


def _artifact_dependency(modules: list[ModuleManifest]) -> bool:
    for producer in modules:
        output_types = {port.artifact_type for port in producer.output_artifacts}
        for consumer in modules:
            if producer.id != consumer.id and output_types & {port.artifact_type for port in consumer.input_artifacts}:
                return True
    return False


def infer_workflows(query: str, *, registry: ModuleRegistry | None = None) -> list[str]:
    active = registry or _DEFAULT_REGISTRY
    normalized_query = _normalize(query)
    dominant_exact_domains = set()
    exact_domains = set()
    for module in active.all():
        exact_phrases = (
            _phrase_matches(query, module.intents)
            + _phrase_matches(query, module.questions)
            + _phrase_matches(query, (module.title,))
        )
        if exact_phrases:
            exact_domains.add(module.domains[0])
        if any(len(_normalize(phrase)) / len(normalized_query) >= 0.75 for phrase in exact_phrases):
            dominant_exact_domains.add(module.domains[0])
    if dominant_exact_domains:
        return _domain_order(dominant_exact_domains)
    domain_scores: dict[str, float] = defaultdict(float)
    for module in active.all():
        score, reasons = _score_module(module, query)
        if reasons:
            workflow = module.domains[0]
            domain_scores[workflow] = max(domain_scores[workflow], score)
    strongest = max(domain_scores.values(), default=0.0)
    query_features = _features(query)
    module_features = {
        module.id: set().union(
            *(
                _features(value)
                for value in (
                    *module.intents,
                    *module.questions,
                    module.title,
                    module.description,
                    *(port.artifact_type.replace("_", " ") for port in (*module.input_artifacts, *module.output_artifacts)),
                )
            )
        )
        for module in active.all()
    }
    feature_frequency = Counter(feature for features in module_features.values() for feature in features)
    specificity_limit = max(2, len(module_features) // 20)
    specific_feature_domains = {
        module.domains[0]
        for module in active.all()
        if _score_module(module, query)[0] >= 5.0
        and any(feature_frequency[feature] <= specificity_limit for feature in query_features & module_features[module.id])
    }
    explicit_primary_domains = {
        module.domains[0]
        for module in active.all()
        if _features(module.domains[0].replace("_", " ")) & query_features
    }
    matched = {
        domain
        for domain, score in domain_scores.items()
        if score >= max(5.0, strongest * 0.35)
    } | exact_domains | explicit_primary_domains | specific_feature_domains
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
    if module.domains[0] in set(workflows):
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
        workflow = module.domains[0]
        if workflow in workflows:
            grouped[workflow].append((score + 2.0, module, reasons or [f"available in matched workflow: {workflow}"]))
    candidates = {}
    selected_by_workflow: dict[str, list[str]] = {}
    assigned_modules = set()
    for workflow in workflows:
        ranked = sorted(grouped[workflow], key=lambda item: (-item[0], item[1].id))
        ranked = [item for item in ranked if item[1].id not in assigned_modules]
        selected_by_workflow[workflow] = _select_ranked_modules(ranked, query)
        candidates[workflow] = [
            {
                "id": module.id,
                "title": module.title,
                "score": round(score, 3),
                "access": module.access,
                "mutability": module.mutability,
                "maturity": module.maturity,
                "selected": module.id in selected_by_workflow[workflow],
                "selection_reasons": reasons,
            }
            for score, module, reasons in ranked[:per_workflow]
        ]
        assigned_modules.update(item["id"] for item in candidates[workflow])
    parallel_requested = any(term in _normalize(query) for term in ("parallel", "并行", "同时"))
    selected_module_ids = [module_id for workflow in workflows for module_id in selected_by_workflow[workflow]]
    selected_modules = [active.get(module_id) for module_id in selected_module_ids]
    dependency_present = _artifact_dependency(selected_modules)
    if len(selected_module_ids) == 1 and len(workflows) == 1:
        plan_type = "single"
    elif len(workflows) == 1:
        plan_type = "serial" if dependency_present else "parallel"
    elif parallel_requested and not (SERIAL_DOMAINS & set(workflows)):
        plan_type = "parallel"
    elif parallel_requested:
        plan_type = "mixed"
    else:
        plan_type = "serial"
    steps = []
    for workflow in workflows:
        if len(workflows) == 1 and plan_type == "parallel":
            mode = "parallel"
        else:
            mode = "parallel" if plan_type in {"parallel", "mixed"} and workflow not in SERIAL_DOMAINS else "serial"
        steps.append({"workflow": workflow, "mode": mode, "selected_module_ids": selected_by_workflow[workflow], "candidates": candidates[workflow]})
    return {"objective": query, "matched_workflows": workflows, "plan_type": plan_type, "selected_module_ids": selected_module_ids, "steps": steps}
