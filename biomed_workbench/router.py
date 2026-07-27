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
GENERIC_DOMAIN_LABELS = frozenset({"evidence"})
_DEFAULT_REGISTRY = ModuleRegistry.discover(BUILTIN_ROOT)
_ASCII_STOP = frozenset(
    {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "then", "to", "with",
        "analyze", "analysis", "assess", "compare", "confidence", "data", "draft", "gene", "identify", "pattern", "patterns",
        "profile", "protein", "retrieve", "result", "results", "retain", "run", "scientific", "summary", "summarize", "test", "tool", "types",
        "validate", "validation", "cell", "rna", "dna",
        "evidence", "grade", "hypothesis", "package", "prepare", "publication-grade", "revise",
        "measurement", "measurements", "observed", "population", "quantify", "quantification", "scenario",
    }
)
_CJK_STOP = frozenset({
    "分析", "数据", "结果", "进行", "检查", "评估", "验证", "科研", "汇总", "工具",
    "保留", "映射", "后续", "区域", "相关", "使用", "处理", "组装", "数据库", "查询",
    "查询", "检索", "核查", "筛查",
})
_CJK_BOUNDARY_CONNECTORS = frozenset({"与", "及", "和", "并"})
_SINGLE_CELL_KEYWORDS = frozenset({
    "单细胞",
    "单细胞RNA",
    "single-cell",
    "single cell",
    "scrna",
    "scRNA",
    "sc-rna",
    "sc rn a",  # defensive token in case separators are normalized
})
_IMAGING_KEYWORDS = frozenset({
    "图像",
    "影像",
    "image",
    "imaging",
    "dicom",
    "nifti",
    "nnunet",
    "nn-unet",
    "mri",
    "ct",
    "pet",
    "dce",
    "t1",
    "t2",
    "adc",
    "radiology",
    "medical",
    "medical imaging",
    "contrast",
    "radiomic",
    "microct",
    "分割",
    "segmentation",
    "cell-migration",
    "cell migration",
    "追踪",
    "时间序列",
    "track",
    "tracking",
    "segment",
})


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
            features.update(
                feature
                for index in range(max(0, len(run) - width + 1))
                if not (
                    (feature := run[index : index + width])[0] in _CJK_BOUNDARY_CONNECTORS
                    or feature[-1] in _CJK_BOUNDARY_CONNECTORS
                )
            )
    if "单细胞" in normalized or "single-cell" in normalized or "single cell" in normalized:
        features.update({"single-cell", "single-cell-rna"})
    if re.search(r"\bscrna(?:[-_]seq|[-_]?seq)?\b", normalized):
        features.update({"single-cell", "single-cell-rna", "single-cell-rna-seq", "ambient", "droplet"})
    if "sc-rna" in normalized or "scrna" in normalized:
        features.update({"single-cell", "single-cell-rna"})
    if "空滴" in normalized or "ambient" in normalized:
        features.update({"droplet", "decontamination", "ambient"})
    return {feature for feature in features if feature not in _CJK_STOP}


def _is_single_cell_query(normalized_query: str) -> bool:
    return bool(
        any(keyword in normalized_query for keyword in _SINGLE_CELL_KEYWORDS)
        or re.search(r"\bsc[-_\s]?rna\b", normalized_query)
        or re.search(r"\bscrna\b", normalized_query)
        or re.search(r"\bscrna[-_ ]?seq\b", normalized_query)
        or re.search(r"\bsc[-_ ]?rnaseq\b", normalized_query)
    )


def _is_single_cell_generic_query(normalized_query: str) -> bool:
    if not _is_single_cell_query(normalized_query):
        return False
    if re.search(
        r"\bdonor|single[-_ ]?donor|供体|整合|注释|注解|通信|marker|trajectory|velocity|fate|pca|聚类|分群|调控|motif|peak|atac|rna\s+velocity|多组学|WNN|MOFA|批次|batch|doublet|ambient|decontamination|标记|基因|differential|差异",
        normalized_query,
    ):
        return False
    if re.search(r"\bempty[ -]?drops?|空滴|decontamin|去噪|去除|清洗|空液滴", normalized_query):
        return False
    if any(term in normalized_query for term in ("analysis", "分析")):
        # Explicit analytic verbs should keep a higher-level module only when explicitly anchored;
        # here we keep generic only for workflow-entry queries.
        return False
    return True


def _is_imaging_query(normalized_query: str) -> bool:
    return any(keyword in normalized_query for keyword in _IMAGING_KEYWORDS)


def _has_regvelo_intent(normalized_query: str) -> bool:
    return bool(
        re.search(r"\bregvelo\b|\bregulatory\s+velocity\b|grn\s+informed", normalized_query)
        or ("cellrank" in normalized_query and "velocity" in normalized_query and "regulatory" in normalized_query)
    )


def _has_scvi_intent(normalized_query: str) -> bool:
    return bool(re.search(r"\bscvi\b", normalized_query) or "scanvi" in normalized_query)


def _phrase_matches(query: str, phrases: Iterable[str]) -> list[str]:
    normalized_query = _normalize(query)
    matches: list[str] = []
    for phrase in phrases:
        normalized_phrase = _normalize(phrase)
        if normalized_phrase not in normalized_query:
            continue
        features = _features(phrase)
        if not features and not re.search(r"[a-z0-9]{3,}", normalized_phrase) and not re.search(r"[\u4e00-\u9fff]{2,}", normalized_phrase):
            continue
        if not normalized_phrase.strip():
            continue
        if len(normalized_phrase) <= 2:
            continue
        matches.append(phrase)
    return matches


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
    has_regvelo = _has_regvelo_intent(normalized)
    has_scvi = _has_scvi_intent(normalized)

    if has_regvelo and not has_scvi:
        ranked = [item for item in ranked if item[1].id != "single-cell-generative-modeling"]

    if _is_single_cell_generic_query(normalized):
        qc_item = next((item for item in ranked if item[1].id == "single-cell-qc"), None)
        if qc_item is not None:
            ranked = [qc_item] + [item for item in ranked if item[1].id != qc_item[1].id]
    multi_intent = any(token in normalized for token in (" and ", " then ", "同时", "并行", "以及", "并且", "并", "然后", "最后", "和"))
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
    if len(exact) == 1:
        exact_score = exact[0][0]
        runner_up_score = next(
            (item[0] for item in ranked if item[1].id != exact[0][1].id),
            0.0,
        )
        if exact_score >= 20.0 and (runner_up_score == 0.0 or exact_score >= runner_up_score * 3.0):
            return [exact[0][1].id]
    if exact and not multi_intent:
        return [item[1].id for item in selected]
    if not multi_intent:
        strong_sources = [
            item for item in ranked
            if item[1].module_type == "data_source" and item[0] >= 25.0 and len(_matched_features(item[1], query)) >= 2
        ]
        if strong_sources:
            return [strong_sources[0][1].id]
        top_score = ranked[0][0]
        runner_up_score = ranked[1][0] if len(ranked) > 1 else 0.0
        if top_score >= 12.0 and (runner_up_score == 0.0 or top_score >= runner_up_score * 2.0):
            return [ranked[0][1].id]
    # When a compound request explicitly names two or more bounded operations,
    # those manifests already define the sufficient route. Context words should
    # not inflate that route into another broad workflow merely because it
    # shares a general assay or artifact term.
    if len(exact) >= 2 and len(_features(query)) < 30:
        return [item[1].id for item in selected]

    if has_regvelo and not has_scvi:
        forced = next((item for item in ranked if item[1].id == "single-cell-regulatory-velocity"), None)
        if forced is not None:
            forced_id = forced[1].id
            if all(forced_id != entry[1].id for entry in selected):
                selected.append(forced)
            dedupe: list[tuple[float, ModuleManifest, list[str]]] = []
            seen: set[str] = set()
            for selected_item in selected:
                module_id = selected_item[1].id
                if module_id in seen:
                    continue
                seen.add(module_id)
                dedupe.append(selected_item)
            selected = dedupe

    top_score = ranked[0][0]
    threshold = max(5.0, top_score * 0.25)
    covered = set().union(*(_matched_features(item[1], query) for item in selected))
    matched_by_module = {item[1].id: _matched_features(item[1], query) for item in ranked}
    feature_frequency = Counter(feature for features in matched_by_module.values() for feature in features)
    specificity_limit = max(2, len(ranked) // 5)
    selection_limit = 24 if len(_features(query)) >= 30 else 16
    for item in ranked:
        score, module, reasons = item
        selected_ids = {chosen[1].id for chosen in selected}
        # A dense scientific request can legitimately name more than ten
        # independent operations. Keep the plan bounded while preserving the
        # explicitly requested breadth for downstream artifact scheduling.
        if module.id in selected_ids or score < threshold or len(selected) >= selection_limit:
            continue
        if not reasons or all(reason.startswith("available in matched workflow") for reason in reasons):
            continue
        if not multi_intent and any(
            module.id in chosen[1].alternatives or chosen[1].id in module.alternatives for chosen in selected
        ):
            continue
        features = matched_by_module[module.id]
        new_features = features - covered
        informative_features = {
            feature for feature in new_features if feature_frequency[feature] <= specificity_limit
        }
        if not informative_features:
            continue
        selected.append(item)
        covered.update(features)
    return [item[1].id for item in selected]


def _request_ordered_modules(
    module_ids: list[str], query: str, registry: ModuleRegistry
) -> list[str]:
    """Order independent selected operations by their explicit request position.

    Artifact dependencies are applied after this lightweight ordering, so a
    producer remains before a consumer even when the user phrases the outcome
    first. This only affects compound requests with otherwise independent
    operations.
    """
    normalized = _normalize(query)

    def position(module_id: str) -> tuple[int, int, str]:
        module = registry.get(module_id)
        exact_positions = [
            normalized.find(_normalize(phrase))
            for phrase in (*module.intents, *module.questions, module.title)
            if len(_normalize(phrase)) >= 4 and _normalize(phrase) in normalized
        ]
        if exact_positions:
            return (min(exact_positions), 0, module_id)
        matched = sorted(_matched_features(module, query), key=lambda value: (-len(value), value))
        positions = [normalized.find(feature) for feature in matched[:5] if normalized.find(feature) >= 0]
        return (min(positions) if positions else len(normalized), 1, module_id)

    ordered = sorted(module_ids, key=position)
    single_cell_generic_query = (
        _is_single_cell_query(normalized)
        and not re.search(
            r"batch|整合|注释|注解|通信|轨迹|velocity|fate|pca|维度|聚类|分群|marker|注释|注解|双细胞|marker|双t|trajectory|trajectory",
            normalized,
        )
    )
    if single_cell_generic_query:
        for idx, module_id in enumerate(ordered):
            if module_id == "single-cell-qc":
                ordered.pop(idx)
                ordered.insert(0, module_id)
                break
    return ordered


def _artifact_dependency(modules: list[ModuleManifest]) -> bool:
    for producer in modules:
        for consumer in modules:
            if producer.id != consumer.id and any(
                ports_compatible(output, required)
                for output in producer.output_artifacts
                for required in consumer.input_artifacts
            ):
                return True
    return False


def _order_by_artifact_dependencies(
    module_ids: list[str], registry: ModuleRegistry
) -> list[str]:
    """Return a stable producer-before-consumer order for selected modules."""
    if len(module_ids) < 2:
        return module_ids
    modules = {module_id: registry.get(module_id) for module_id in module_ids}
    original_position = {module_id: index for index, module_id in enumerate(module_ids)}
    dependencies = {module_id: set() for module_id in module_ids}
    for producer_id, producer in modules.items():
        for consumer_id, consumer in modules.items():
            if producer_id == consumer_id:
                continue
            if any(
                ports_compatible(output, required)
                for output in producer.output_artifacts
                for required in consumer.input_artifacts
            ):
                dependencies[consumer_id].add(producer_id)
    ordered: list[str] = []
    remaining = set(module_ids)
    while remaining:
        ready = sorted(
            (module_id for module_id in remaining if not (dependencies[module_id] & remaining)),
            key=original_position.__getitem__,
        )
        if not ready:
            return module_ids
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def ports_compatible(produced, required) -> bool:
    """Return whether two manifest ports can exchange one typed artifact."""
    if produced.artifact_type != required.artifact_type:
        return False
    for output_format in produced.formats:
        for input_format in required.formats:
            if output_format.name != input_format.name or not set(output_format.versions) & set(input_format.versions):
                continue
            if not set(output_format.compression) & set(input_format.compression):
                continue
            if not set(output_format.orientations) & set(input_format.orientations):
                continue
            if input_format.coordinate_systems and not set(output_format.coordinate_systems) & set(input_format.coordinate_systems):
                continue
            if input_format.genome_build_policy != "not_applicable" and not set(output_format.genome_builds) & set(input_format.genome_builds):
                continue
            if input_format.annotation_releases and not set(output_format.annotation_releases) & set(input_format.annotation_releases):
                continue
            return True
    return False


def _expand_required_upstreams(module_ids: list[str], registry: ModuleRegistry) -> list[str]:
    """Add manifest-declared prerequisite producers without keyword-specific rules."""
    manifests = {manifest.id: manifest for manifest in registry.all()}
    maturity_rank = {"reference": 0, "validated": 1, "experimental": 2}
    ordered: list[str] = []
    visiting: set[str] = set()

    def add(module_id: str) -> None:
        if module_id in ordered:
            return
        if module_id in visiting:
            return
        visiting.add(module_id)
        consumer = manifests[module_id]
        for required_port in consumer.input_artifacts:
            if required_port.source_policy != "upstream_required":
                continue
            candidates = [
                producer
                for producer in manifests.values()
                if producer.id != module_id
                and any(ports_compatible(output_port, required_port) for output_port in producer.output_artifacts)
            ]
            if candidates:
                selected = min(candidates, key=lambda item: (maturity_rank[item.maturity], len(item.credentials), item.id))
                add(selected.id)
        visiting.remove(module_id)
        ordered.append(module_id)

    for module_id in module_ids:
        add(module_id)
    return ordered


def infer_workflows(query: str, *, registry: ModuleRegistry | None = None) -> list[str]:
    active = registry or _DEFAULT_REGISTRY
    normalized_query = _normalize(query)
    single_cell_query = _is_single_cell_query(normalized_query)
    imaging_query = _is_imaging_query(normalized_query)
    dominant_exact_domains = set()
    exact_domains = set()
    direct_source_exact_domains = set()
    for module in active.all():
        exact_phrases = (
            _phrase_matches(query, module.intents)
            + _phrase_matches(query, module.questions)
            + _phrase_matches(query, (module.title,))
        )
        if exact_phrases:
            exact_domains.add(module.domains[0])
            if module.module_type == "data_source":
                direct_source_exact_domains.add(module.domains[0])
            if len(module.domains) > 1:
                for extra_domain in module.domains[1:]:
                    label = re.escape(_normalize(extra_domain.replace("_", " "))).replace(r"\\ ", r"[\\s_-]+")
                    if re.search(rf"(?<![a-z0-9]){label}(?![a-z0-9])", normalized_query):
                        exact_domains.add(extra_domain)
                        if module.module_type == "data_source":
                            direct_source_exact_domains.add(extra_domain)
        if any(len(_normalize(phrase)) / len(normalized_query) >= 0.75 for phrase in exact_phrases):
            dominant_exact_domains.add(module.domains[0])
    if dominant_exact_domains:
        return _domain_order(dominant_exact_domains)
    multi_intent = any(
        token in normalized_query
        for token in (" and ", " then ", "同时", "并行", "以及", "并且", "然后", "最后", "和")
    )
    # An explicit, standalone source lookup is already a bounded operation.
    # Broad assay words in its description must not add unrelated analysis
    # workflows unless the request explicitly joins another operation.
    if direct_source_exact_domains and not multi_intent:
        return _domain_order(direct_source_exact_domains)
    # A standalone exact scientific operation is already an unambiguous route.
    # Generic context terms such as "time series" or "image" must not add a
    # second workflow merely because a broad module happens to share them.
    if exact_domains and not multi_intent:
        return _domain_order(exact_domains)
    domain_scores: dict[str, float] = defaultdict(float)
    for module in active.all():
        score, reasons = _score_module(module, query)
        if reasons:
            workflow = module.domains[0]
            domain_scores[workflow] = max(domain_scores[workflow], score)
    strongest = max(domain_scores.values(), default=0.0)
    if not multi_intent and strongest >= 20.0:
        top_workflow = max(domain_scores, key=domain_scores.get, default="evidence")
        return [top_workflow]
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
    feature_domain_frequency: dict[str, Counter[str]] = defaultdict(Counter)
    for module in active.all():
        for feature in module_features[module.id]:
            feature_domain_frequency[feature][module.domains[0]] += 1
    specificity_limit = max(2, len(module_features) // 20)
    specific_feature_domains = set()
    for module in active.all():
        if _score_module(module, query)[0] < 5.0:
            continue
        matching_features = query_features & module_features[module.id]
        rare_matches = {
            feature for feature in matching_features if len(feature) >= 3 and feature_frequency[feature] <= specificity_limit
        }
        has_domain_unique_match = any(len(feature_domain_frequency[feature]) == 1 for feature in rare_matches)
        if has_domain_unique_match or len(rare_matches) >= 2:
            specific_feature_domains.add(module.domains[0])
    domain_concentrated_feature_domains = set()
    for feature in query_features:
        counts = feature_domain_frequency.get(feature)
        if not counts:
            continue
        dominant_domain, dominant_count = counts.most_common(1)[0]
        tied = sum(count == dominant_count for count in counts.values()) > 1
        concentration = dominant_count / sum(counts.values())
        if len(feature) >= 3 and not tied and (len(counts) == 1 or concentration >= 0.8):
            if domain_scores.get(dominant_domain, 0.0) >= 5.0:
                domain_concentrated_feature_domains.add(dominant_domain)
    explicit_primary_domains = set()
    for module in active.all():
        domain = module.domains[0]
        if domain in GENERIC_DOMAIN_LABELS:
            continue
        label = re.escape(_normalize(domain.replace("_", " "))).replace(r"\ ", r"[\s_-]+")
        if re.search(rf"(?<![a-z0-9]){label}(?![a-z0-9])", normalized_query):
            explicit_primary_domains.add(domain)
    def _has_single_cell_manifest_signal(candidate: ModuleManifest) -> bool:
        searchable = (*candidate.intents, *candidate.questions, candidate.title)
        return any("single-cell" in _features(value) for value in searchable)
    matched = {
        domain
        for domain, score in domain_scores.items()
        if score >= max(5.0, strongest * 0.35)
    } | exact_domains | explicit_primary_domains | specific_feature_domains | domain_concentrated_feature_domains
    if single_cell_query and not imaging_query:
        matched.discard("imaging")
    if single_cell_query and not matched:
        matched_single_cell = {
            module.domains[0]
            for module in active.all()
            if module.domains[0] in PREFERRED_DOMAIN_ORDER
            and _score_module(module, query)[0] >= 3.5
            and _has_single_cell_manifest_signal(module)
        }
        if "omics" in matched_single_cell:
            matched.add("omics")
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
        selected_by_workflow[workflow] = _order_by_artifact_dependencies(
            _request_ordered_modules(_select_ranked_modules(ranked, query), query, active),
            active,
        )
        selected_by_workflow[workflow] = _expand_required_upstreams(selected_by_workflow[workflow], active)
        selected_ids = set(selected_by_workflow[workflow])
        selected_ranked = [item for item in ranked if item[1].id in selected_ids]
        visible_ranked = selected_ranked[:per_workflow]
        if len(visible_ranked) < per_workflow:
            non_selected = [
                item
                for item in ranked
                if item[1].id not in selected_ids
            ]
            visible_ranked.extend(non_selected[: per_workflow - len(visible_ranked)])
        visible_ids = {module.id for _score, module, _reasons in visible_ranked}
        if set(selected_ids) - visible_ids:
            visible_ranked.extend(
                item for item in selected_ranked if item[1].id not in visible_ids
            )
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
            for score, module, reasons in visible_ranked
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
