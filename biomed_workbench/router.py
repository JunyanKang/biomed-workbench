"""Dynamic routing from project intent to independently registered modules."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .models import Capability
from .minimal_sufficient import select_minimal_sufficient
from .objective_compiler import compile_objective, ports_compatible
from .modules.contract import ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry, ModuleRegistryError
from .scientific_semantics import (
    AXES as SEMANTIC_AXES,
    ScientificSemanticBrief,
    module_semantic_concepts,
    parse_scientific_semantics,
)


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


def _validation_scopes(registry: ModuleRegistry) -> dict[str, dict[str, bool | None]]:
    """Read only a readiness report bound to the active registry digest."""
    path = Path(BUILTIN_ROOT).resolve().parents[2] / "reports" / "execution-readiness.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if payload.get("registry_digest") != registry.digest:
        return {}
    return {
        str(record["module_id"]): {
            "engineering_validated": record.get("engineering_validated"),
            "method_validated": record.get("method_validated"),
            "project_promoted": False,
        }
        for record in payload.get("records", [])
        if isinstance(record, dict) and isinstance(record.get("module_id"), str)
    }
_SINGLE_CELL_KEYWORDS = frozenset({
    "单细胞",
    "单细胞RNA",
    "single-cell",
    "single cell",
    "scrna",
    "scrna-seq",
    "scRNA",
    "sc-rna",
    "sc rn a",  # defensive token in case separators are normalized
    "h5ad",
    "seurat",
    "scanpy",
    "scvi",
    "scanvi",
    "celltypist",
    "azimuth",
    "popv",
    "scrublet",
    "scdblfinder",
    "soupx",
    "cellbender",
    "emptydrops",
    "cellchat",
    "nichenet",
    "cellphonedb",
    "regvelo",
    "scvelo",
    "cellrank",
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
        or re.search(r"\b(harmony|scanorama|bbknn|rna velocity|cite[-_ ]?seq|wnn|mofa\+?|scenic\+?|liana)\b", normalized_query)
    )


def _is_imaging_query(normalized_query: str) -> bool:
    for keyword in _IMAGING_KEYWORDS:
        normalized_keyword = _normalize(keyword)
        if re.search(r"[\u3400-\u9fff]", normalized_keyword):
            if normalized_keyword in normalized_query:
                return True
        elif re.search(r"^[a-z0-9]+(?:[- ][a-z0-9]+)*$", normalized_keyword):
            pattern = re.escape(normalized_keyword).replace(r"\ ", r"[\s_-]+")
            if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalized_query):
                return True
        elif normalized_keyword in normalized_query:
            return True
    return False


def _is_molecular_design_query(normalized_query: str) -> bool:
    structural_or_design = bool(
        re.search(
            r"\b(primer|pcr|amplicon|crispr|guide|restriction|digest|golden[ -]?gate|cloning|plasmid|orf|open reading frame|sanger|docking|haddock3|ligand|smiles|protein structure|structure quality|alphafold ?3|metascape|msbio2)\b",
            normalized_query,
        )
        or any(term in normalized_query for term in ("引物", "酶切", "克隆", "质粒", "结构质量", "分子对接"))
    )
    protein_network = bool(re.search(r"\b(protein interaction|protein-interaction|ppi)\b", normalized_query))
    assay_bound_interaction = bool(re.search(r"\b(ip[-–— ]?ms|ap[-–— ]?ms|immunoprecipitation mass spectrometry)\b", normalized_query))
    return structural_or_design or (protein_network and not assay_bound_interaction)


def _is_omics_assay_query(normalized_query: str) -> bool:
    return bool(
        re.search(
            r"\b(fastq|fastqc|fastp|multiqc|bwa|samtools|bam|cram|vcf|tabix|bgzip|variant|peak|motif|atac|chip[- ]?seq|cut&tag|cut&run|rna[- ]?seq|expression qc|differential expression|nmf|gwas|fine mapping|read[- ]?quality|contamination screen)\b",
            normalized_query,
        )
        or any(term in normalized_query for term in ("测序", "比对", "峰", "变异", "差异表达", "富集", "组学"))
    )


def _is_publication_query(normalized_query: str) -> bool:
    return bool(
        re.search(
            r"\b(manuscript|paper|publication|publish|citation|reviewer|response|patent|presentation|figure|"
            r"claim[- ]?evidence|grant|proposal|specific aims?|data availability|paper reader|full[- ]?paper reading)\b",
            normalized_query,
        )
        or any(
            term in normalized_query
            for term in (
                "论文", "稿件", "审稿", "返修", "引用", "专利", "发表", "图表", "基金申请", "申请书",
                "研究计划书", "全文精读", "中英对照", "数据可用性", "演示文稿", "学术写作", "语言修订",
            )
        )
    )


def _artifact_routing_context(query: str) -> dict[str, Any]:
    """Describe the supplied material before selecting scientific operations."""
    normalized = _normalize(query)
    proposal = bool(
        re.search(r"\b(?:grant|proposal|specific aims?|nsfc)\b", normalized)
        or any(term in normalized for term in ("基金申请", "项目书", "申请书", "国自然", "国家自然科学基金"))
    )
    patent = bool(re.search(r"\bpatent\b", normalized) or "专利" in normalized)
    journal = _is_journal_targeting_query(normalized)
    summary_table = bool(
        re.search(r"\.(?:xlsx|xls|csv|tsv)\b", normalized)
        or re.search(r"\b(?:summary spreadsheet|summary table|processed table|result table)\b", normalized)
        or any(term in normalized for term in ("汇总表", "结果表", "统计表", "整理后的表格"))
    )
    raw_or_reanalysis = bool(
        re.search(r"\b(?:fastq|bam|cram|h5ad|loom|raw counts?|count matrix|fragment file|reanaly[sz]e|rerun)\b", normalized)
        or any(term in normalized for term in ("原始数据", "原始计数", "重新分析", "重跑", "从头分析"))
    )
    docx = bool(re.search(r"\.docx\b|\bword\b", normalized) or "Word" in query or "文档交付" in normalized)
    return {
        "proposal": proposal,
        "patent_explicit": patent,
        "journal_targeting_explicit": journal,
        "summary_table": summary_table,
        "raw_or_reanalysis_explicit": raw_or_reanalysis,
        "docx_delivery": docx,
        "interpretation_only": summary_table and not raw_or_reanalysis,
    }


def _is_journal_targeting_query(normalized_query: str) -> bool:
    """Return whether a publication request actually asks for journal fit or rules."""
    return bool(
        re.search(
            r"\b(journal|target journal|journal fit|author guidelines?|format requirements?|submission requirements?|word limit)\b",
            normalized_query,
        )
        or any(term in normalized_query for term in ("期刊", "投稿规范", "作者指南", "格式要求", "字数限制", "选刊"))
    )


def _is_clinical_query(normalized_query: str) -> bool:
    return bool(
        re.search(r"\b(clinical|patient|cohort|survival|biomarker|adverse|trial|tumou?r|cancer|de[- ]?identif)\b", normalized_query)
        or any(term in normalized_query for term in ("临床", "患者", "队列", "生存", "不良事件", "肿瘤"))
    )


def _is_wetlab_query(normalized_query: str) -> bool:
    return bool(
        re.search(r"\b(qpcr|flow cytometry|fcs|western blot|cfu|dose response|growth curve|dilution|annexin|viability|xenograft|radiotracer|immunoassay)\b", normalized_query)
        or any(term in normalized_query for term in ("流式", "蛋白印迹", "稀释", "剂量", "细菌", "活性", "成像"))
    )


def _is_evidence_query(normalized_query: str) -> bool:
    return bool(
        re.search(r"\b(evidence|retrieve|search|database|ncbi|entrez|uniprot|ensembl|dbsnp|gnomad|hpo|go|reactome|cbioportal|opentargets|crossref|europe pmc|biorxiv|pubchem|rcsb|alphafold|string|ppi)\b", normalized_query)
        or any(term in normalized_query for term in ("证据", "数据库", "检索", "查询", "文献"))
    )


def _has_exact_route_signal(module: ModuleManifest, query: str) -> bool:
    return bool(
        _phrase_matches(query, module.routing.method_aliases)
        or
        _phrase_matches(query, module.intents)
        or _phrase_matches(query, module.questions)
        or _phrase_matches(query, (module.title,))
    )


def _semantic_module_allowed(module: ModuleManifest, brief: ScientificSemanticBrief) -> bool:
    concepts = module_semantic_concepts(module)
    if not any(concepts.values()):
        return True
    if any(set(concepts[axis]) & set(brief.negated_concepts[axis]) for axis in SEMANTIC_AXES):
        return False
    query_core = set(brief.concepts["assays"]) | set(brief.concepts["targets"]) | set(brief.concepts["relations"])
    module_core = set(concepts["assays"]) | set(concepts["targets"]) | set(concepts["relations"])
    if not query_core:
        return True
    return bool(query_core & module_core)


def _semantic_module_explicitly_negated(module: ModuleManifest, brief: ScientificSemanticBrief) -> bool:
    """Return whether an explicit request conflicts with a parsed negative constraint.

    Exact method names are stronger evidence than an incomplete ontology match,
    but they must never override an explicit exclusion such as "do not run RNA
    secondary-structure analysis".
    """
    concepts = module_semantic_concepts(module)
    return any(
        set(concepts[axis]) & set(brief.negated_concepts[axis])
        for axis in SEMANTIC_AXES
    )


def _module_allowed_for_query(
    module: ModuleManifest,
    query: str,
    semantic_brief: ScientificSemanticBrief | None = None,
) -> bool:
    normalized_query = _normalize(query)
    artifact_context = _artifact_routing_context(query)
    if artifact_context["proposal"] and not artifact_context["patent_explicit"] and (
        module.id.startswith("patent-") or "patent" in module.id
    ):
        return False
    if artifact_context["proposal"] and not artifact_context["journal_targeting_explicit"] and module.id == "journal-targeting-and-compliance":
        return False
    if artifact_context["interpretation_only"] and module.id.startswith("single-cell-"):
        return False
    if any(_normalize(term) in normalized_query for term in module.routing.exclusion_terms):
        return False
    if module.routing.required_any_terms and not any(
        _normalize(term) in normalized_query for term in module.routing.required_any_terms
    ):
        return False
    brief = semantic_brief or parse_scientific_semantics(query)
    if _has_exact_route_signal(module, query):
        return not _semantic_module_explicitly_negated(module, brief)
    if not _semantic_module_allowed(module, brief):
        return False
    single_cell_query = _is_single_cell_query(normalized_query)
    omics_query = _is_omics_assay_query(normalized_query)
    molecular_query = _is_molecular_design_query(normalized_query)
    if any("single-cell" in _features(alias) for alias in module.routing.method_aliases) and not single_cell_query:
        return False
    if module.domains[0] == "imaging" and not _is_imaging_query(normalized_query):
        return False
    if module.domains[0] == "publication" and not _is_publication_query(normalized_query):
        return False
    if module.domains[0] == "wetlab" and omics_query and not _is_wetlab_query(normalized_query):
        return False
    if module.domains[0] == "evidence" and omics_query and not _is_evidence_query(normalized_query):
        return False
    if (
        module.domains[0] == "omics"
        and molecular_query
        and not omics_query
        and not _has_exact_route_signal(module, query)
    ):
        return False
    if (
        module.domains[0] == "molecular_design"
        and brief.concepts["assays"]
        and not molecular_query
        and not _has_exact_route_signal(module, query)
    ):
        return False
    return True


def _forced_named_method_module_ids(normalized_query: str, modules: Iterable[ModuleManifest]) -> list[str]:
    """Resolve explicitly named methods solely from versioned manifest metadata."""
    matches = []
    for module in modules:
        exact = _phrase_matches(normalized_query, module.routing.method_aliases)
        if exact and module.routing.named_method_priority > 0:
            matches.append((module.routing.named_method_priority, max(map(len, exact)), module.id))
    return [module_id for _priority, _length, module_id in sorted(matches, key=lambda item: (-item[0], -item[1], item[2]))]


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


def _score_module(
    module: ModuleManifest,
    query: str,
    semantic_brief: ScientificSemanticBrief | None = None,
) -> tuple[float, list[str]]:
    brief = semantic_brief or parse_scientific_semantics(query)
    query_features = _features(query)
    exact_intents = _phrase_matches(query, module.intents)
    exact_questions = _phrase_matches(query, module.questions)
    title_exact = _phrase_matches(query, (module.title,))
    alias_exact = _phrase_matches(query, module.routing.method_aliases)
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
    score += (module.routing.named_method_priority / 5.0) * len(alias_exact)
    score += 3.5 * len(intent_overlap)
    score += 2.5 * len(question_overlap)
    score += 3.0 * len(title_overlap)
    score += 0.75 * len(description_overlap)
    score += 1.5 * len(artifact_overlap)
    semantic = module_semantic_concepts(module)
    semantic_matches = {
        axis: sorted(set(semantic[axis]) & set(brief.concepts[axis]))
        for axis in SEMANTIC_AXES
    }
    score += 24.0 * len(semantic_matches["assays"])
    score += 12.0 * len(semantic_matches["targets"])
    score += 4.0 * len(semantic_matches["controls"])
    score += 6.0 * len(semantic_matches["normalizations"])
    score += 10.0 * len(semantic_matches["relations"])
    if module.access == "offline":
        score += 0.25
    reasons = []
    if exact_intents:
        reasons.append(f"exact intent: {exact_intents[0]}")
    if alias_exact:
        reasons.append(f"named method: {alias_exact[0]}")
    if title_exact:
        reasons.append("title matches the request")
    concepts = sorted(intent_overlap | question_overlap | title_overlap | artifact_overlap, key=lambda value: (-len(value), value))
    if concepts:
        reasons.append(f"matched concepts: {', '.join(concepts[:5])}")
    if not reasons and description_overlap:
        reasons.append(f"description concepts: {', '.join(sorted(description_overlap)[:5])}")
    for axis in SEMANTIC_AXES:
        if semantic_matches[axis]:
            reasons.append(f"scientific {axis}: {', '.join(semantic_matches[axis])}")
    return score, reasons


def _expand_semantic_coverage(
    selected_ids: list[str],
    ranked: list[tuple[float, ModuleManifest, list[str]]],
    brief: ScientificSemanticBrief,
) -> list[str]:
    """Add the best eligible module for every resolved scientific concept."""
    selected = list(selected_ids)
    by_id = {item[1].id: item[1] for item in ranked}
    covered = {
        axis: {
            concept
            for module_id in selected
            if module_id in by_id
            for concept in module_semantic_concepts(by_id[module_id])[axis]
        }
        for axis in SEMANTIC_AXES
    }
    for axis in SEMANTIC_AXES:
        for concept in brief.concepts[axis]:
            if concept in covered[axis]:
                continue
            candidates = [
                item for item in ranked
                if concept in module_semantic_concepts(item[1])[axis] and item[2]
            ]
            if not candidates:
                continue
            chosen = candidates[0][1]
            if chosen.id not in selected:
                selected.append(chosen.id)
                for candidate_axis in covered:
                    covered[candidate_axis].update(module_semantic_concepts(chosen)[candidate_axis])
    return selected


def _requires_semantic_expansion(brief: ScientificSemanticBrief) -> bool:
    """Return whether the objective is a compound scientific programme."""
    core_count = sum(
        len(brief.concepts[axis])
        for axis in ("assays", "targets", "relations")
    )
    return bool(
        core_count >= 4
        or len(brief.concepts["assays"]) >= 2
        or "cross-modal-concordance" in brief.concepts["relations"]
    )


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
    forced_named_ids = _forced_named_method_module_ids(normalized, (item[1] for item in ranked))

    multi_intent = any(token in normalized for token in (" and ", " then ", "同时", "并行", "以及", "并且", "并", "然后", "最后", "和"))
    exact = [item for item in ranked if any(reason.startswith("exact intent:") or reason == "title matches the request" for reason in item[2])]
    selected: list[tuple[float, ModuleManifest, list[str]]] = exact[:] if exact else [ranked[0]]
    selected_ids = {item[1].id for item in selected}
    for forced_id in forced_named_ids:
        forced_item = next((item for item in ranked if item[1].id == forced_id), None)
        if forced_item is not None and forced_id not in selected_ids:
            selected.append(forced_item)
            selected_ids.add(forced_id)
    forced_single_cell_ids = [
        module_id for module_id in forced_named_ids
        if any(item[1].id == module_id and _is_single_cell_query(normalized) for item in ranked)
    ]
    # Alternatives are mutually substitutable implementations, not parallel
    # workflow steps. For a dense single-cell program, however, the explicitly
    # forced modules are complementary stages and must all remain available.
    if not forced_named_ids:
        nonredundant: list[tuple[float, ModuleManifest, list[str]]] = []
        for item in sorted(selected, key=lambda value: (-value[0], value[1].id)):
            module = item[1]
            if any(
                module.id in kept[1].alternatives or kept[1].id in module.alternatives
                for kept in nonredundant
            ):
                continue
            nonredundant.append(item)
        selected = nonredundant
    if forced_single_cell_ids:
        selected_ids = {item[1].id for item in selected}
        for forced_id in forced_single_cell_ids:
            forced_item = next((item for item in ranked if item[1].id == forced_id), None)
            if forced_item is not None and forced_id not in selected_ids:
                selected.append(forced_item)
                selected_ids.add(forced_id)
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
    if len(exact) >= 2 and len(_features(query)) < 18 and not forced_single_cell_ids:
        return [item[1].id for item in selected]

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
    return ordered


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
    artifact_context = _artifact_routing_context(query)
    semantic_brief = parse_scientific_semantics(query)
    single_cell_query = _is_single_cell_query(normalized_query)
    imaging_query = _is_imaging_query(normalized_query)
    wetlab_query = _is_wetlab_query(normalized_query)
    forced_named_ids = _forced_named_method_module_ids(normalized_query, active.all())
    forced_named_domains = {active.get(module_id).domains[0] for module_id in forced_named_ids}
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
        if any(len(_normalize(phrase)) / len(normalized_query) >= 0.75 for phrase in exact_phrases):
            dominant_exact_domains.add(module.domains[0])
    if dominant_exact_domains:
        return _domain_order(dominant_exact_domains)
    multi_intent = any(
        token in normalized_query
        for token in (" and ", " then ", "同时", "并行", "以及", "并且", "然后", "最后", "和")
    )
    if forced_named_domains and not multi_intent:
        return _domain_order(forced_named_domains)
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
    # A named wet-lab measurement such as Western blot remains a wet-lab
    # quantification request even when it also mentions normalization. Generic
    # normalization language must not redirect it to a sequencing assay.
    if wetlab_query and not _is_omics_assay_query(normalized_query) and not multi_intent:
        return ["wetlab"]
    domain_scores: dict[str, float] = defaultdict(float)
    for module in active.all():
        score, reasons = _score_module(module, query, semantic_brief)
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
        if _score_module(module, query, semantic_brief)[0] < 5.0:
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
    semantic_domains = {
        module.domains[0]
        for module in active.all()
        if _semantic_module_allowed(module, semantic_brief)
        and any(
            set(module_semantic_concepts(module)[axis]) & set(semantic_brief.concepts[axis])
            for axis in ("assays", "targets", "normalizations", "relations")
        )
    }
    matched = {
        domain
        for domain, score in domain_scores.items()
        if score >= max(5.0, strongest * 0.35)
    } | exact_domains | explicit_primary_domains | specific_feature_domains | domain_concentrated_feature_domains | forced_named_domains | semantic_domains
    if artifact_context["proposal"]:
        matched.add("publication")
        if _is_evidence_query(normalized_query):
            matched.add("evidence")
        if not _is_omics_assay_query(normalized_query):
            matched.discard("omics")
    if single_cell_query and not imaging_query:
        matched.discard("imaging")
    if _is_omics_assay_query(normalized_query) and not _is_wetlab_query(normalized_query):
        matched.discard("wetlab")
    if _is_omics_assay_query(normalized_query) and not _is_evidence_query(normalized_query):
        matched.discard("evidence")
    if _is_molecular_design_query(normalized_query):
        if not imaging_query:
            matched.discard("imaging")
        if not _is_publication_query(normalized_query):
            matched.discard("publication")
        if not _is_clinical_query(normalized_query):
            matched.discard("clinical")
    elif re.search(r"\balphafold\b", normalized_query) and _is_evidence_query(normalized_query):
        # A plain AlphaFold DB/confidence request belongs to evidence retrieval.
        # Molecular design is added only by an explicit AF3, docking, ligand,
        # structure-design, or other molecular-design signal.
        matched.discard("molecular_design")
    elif semantic_brief.concepts["assays"] and "molecular_design" not in forced_named_domains:
        # Assay-bound protein-interaction evidence (for example IP-MS) remains
        # in the omics branch unless the request independently names a
        # molecular-design method such as docking or AlphaFold 3.
        matched.discard("molecular_design")
    omics_semantic_assays = {
        "bulk-rna-seq", "single-cell-rna", "single-nucleus-rna", "three-prime-single-nucleus-rna",
        "single-cell-multiome", "cuttag", "s9-6-cuttag", "ip-ms",
    }
    if (
        set(semantic_brief.concepts["assays"])
        and set(semantic_brief.concepts["assays"]) <= omics_semantic_assays
    ):
        explicitly_requested_domains = {"omics"} | forced_named_domains
        if _is_publication_query(normalized_query):
            explicitly_requested_domains.add("publication")
        if _is_clinical_query(normalized_query):
            explicitly_requested_domains.add("clinical")
        if _is_wetlab_query(normalized_query):
            explicitly_requested_domains.add("wetlab")
        if _is_molecular_design_query(normalized_query):
            explicitly_requested_domains.add("molecular_design")
        if _is_imaging_query(normalized_query):
            explicitly_requested_domains.add("imaging")
        if _is_evidence_query(normalized_query):
            explicitly_requested_domains.add("evidence")
        matched &= explicitly_requested_domains
    if single_cell_query and not matched:
        matched_single_cell = {
            module.domains[0]
            for module in active.all()
            if module.domains[0] in PREFERRED_DOMAIN_ORDER
            and _score_module(module, query, semantic_brief)[0] >= 3.5
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
    semantic_brief = parse_scientific_semantics(query)
    artifact_context = _artifact_routing_context(query)
    validation_scopes = _validation_scopes(active)
    workflows = infer_workflows(query, registry=active)
    grouped: dict[str, list[tuple[float, ModuleManifest, list[str]]]] = defaultdict(list)
    for module in active.all():
        if not _module_allowed_for_query(module, query, semantic_brief):
            continue
        score, reasons = _score_module(module, query, semantic_brief)
        workflow = module.domains[0]
        if workflow in workflows:
            grouped[workflow].append((score + 2.0, module, reasons or [f"available in matched workflow: {workflow}"]))
    candidates = {}
    selected_by_workflow: dict[str, list[str]] = {}
    assigned_modules = set()
    for workflow in workflows:
        ranked = sorted(grouped[workflow], key=lambda item: (-item[0], item[1].id))
        ranked = [item for item in ranked if item[1].id not in assigned_modules]
        initially_selected = _select_ranked_modules(ranked, query)
        semantically_complete = (
            _expand_semantic_coverage(initially_selected, ranked, semantic_brief)
            if _requires_semantic_expansion(semantic_brief)
            else initially_selected
        )
        selected_by_workflow[workflow] = _order_by_artifact_dependencies(
            _request_ordered_modules(semantically_complete, query, active),
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
                "registry_contract_label": module.maturity,
                "registry_contract_label_is_scientific_completion": False,
                "validation_scope": validation_scopes.get(module.id, {
                    "engineering_validated": None,
                    "method_validated": None,
                    "project_promoted": False,
                    "reason": "current registry-bound readiness report is unavailable",
                }),
                "selected": module.id in selected_by_workflow[workflow],
                "selection_reasons": reasons,
            }
            for score, module, reasons in visible_ranked
        ]
        assigned_modules.update(item["id"] for item in candidates[workflow])
    selected_module_ids = list(dict.fromkeys(
        module_id for workflow in workflows for module_id in selected_by_workflow[workflow]
    ))
    selected_modules = tuple(active.get(module_id) for module_id in selected_module_ids)
    compiled = compile_objective(query, selected_modules)
    scores_by_id = {
        module.id: score
        for workflow in workflows
        for score, module, _reasons in grouped[workflow]
        if module.id in selected_module_ids
    }
    minimal_sufficient = select_minimal_sufficient(
        selected_modules,
        semantic_brief,
        scores=scores_by_id,
        dependencies=compiled["dependencies"],
    )
    execution_module_ids = list(minimal_sufficient["approved_module_ids"])
    if selected_module_ids and not execution_module_ids:
        # The semantic contract is introduced incrementally across the mature
        # registry. A bounded exact route must remain executable while its
        # manifest is still untyped; describe that compatibility path rather
        # than silently returning an empty execution plan.
        execution_module_ids = list(selected_module_ids)
        minimal_sufficient = {
            **minimal_sufficient,
            "approved_module_ids": list(execution_module_ids),
            "approved_choices": [
                {
                    "module_id": module_id,
                    "role": "bounded-explicit-request",
                    "branch_ids": ["untyped-exact-route"],
                    "decision_information": "explicitly requested registered operation pending typed semantic migration",
                }
                for module_id in execution_module_ids
            ],
            "compatibility_fallback": (
                "No selected module yet carries a typed scientific-semantics contract; "
                "the bounded explicit route remains executable and is not presented as a minimal-method comparison."
            ),
        }
    execution_modules = tuple(active.get(module_id) for module_id in execution_module_ids)
    execution_graph = compile_objective(query, execution_modules) if execution_modules else None
    for workflow in workflows:
        execution_set = set(execution_module_ids)
        for candidate in candidates[workflow]:
            candidate["approved_for_execution"] = candidate["id"] in execution_set
    selected_semantics = {
        axis: {
            concept: [
                module.id for module in selected_modules
                if concept in module_semantic_concepts(module)[axis]
            ]
            for concept in semantic_brief.concepts[axis]
        }
        for axis in SEMANTIC_AXES
    }
    unresolved = [
        {"axis": axis, "concept": concept, "status": "no-eligible-registered-module"}
        for axis in SEMANTIC_AXES
        for concept, module_ids in selected_semantics[axis].items()
        if not module_ids
    ]
    requires_integration = (
        "cross-modal-concordance" in semantic_brief.concepts["relations"]
        and len({concept for concept, ids in selected_semantics["assays"].items() if ids}) >= 2
    )
    integration_node = None
    if requires_integration:
        integration_node = {
            "id": "objective-level-scientific-integration",
            "kind": "reviewed-result-synthesis",
            "depends_on": list(execution_module_ids),
            "requires": "observed, reloaded and scientifically reviewed branch artifacts",
            "purpose": "Reconcile direct, indirect, concordant, discordant and unresolved evidence without converting association into causality.",
        }
        compiled["integration_node"] = integration_node
        compiled["plan_type"] = "mixed"
    plan_type = compiled["plan_type"]
    steps = []
    for workflow in workflows:
        if len(workflows) == 1 and plan_type == "parallel":
            mode = "parallel"
        else:
            mode = "parallel" if plan_type in {"parallel", "mixed"} and workflow not in SERIAL_DOMAINS else "serial"
        steps.append({"workflow": workflow, "mode": mode, "selected_module_ids": selected_by_workflow[workflow], "candidates": candidates[workflow]})
    return {
        "objective": query,
        "artifact_context": artifact_context,
        "matched_workflows": workflows,
        "plan_type": plan_type,
        "selected_module_ids": selected_module_ids,
        "execution_module_ids": execution_module_ids,
        "steps": steps,
        "objective_graph": compiled,
        "execution_graph": execution_graph,
        "minimal_sufficient_analysis": minimal_sufficient,
        "scientific_semantics": semantic_brief.to_dict(),
        "semantic_coverage": selected_semantics,
        "unresolved_semantic_requirements": unresolved,
        "integration_node": integration_node,
    }
