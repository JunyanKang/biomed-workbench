"""Parse scientific intent before module scoring.

The parser is deliberately bounded: it resolves research-design concepts that
change method eligibility, records the exact source phrase and negation state,
and leaves unsupported concepts visible.  It never treats lexical proximity as
proof that a method answers the question.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable


AXES = ("assays", "targets", "controls", "normalizations", "relations")


_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "assays": {
        "bulk-rna-seq": ("bulk rna-seq", "bulk rnaseq", "rna-seq", "rnaseq", "bulk transcriptome"),
        "single-cell-rna": ("single-cell rna", "single cell rna", "scrna-seq", "scrna"),
        "single-nucleus-rna": ("single-nucleus rna", "single nucleus rna", "snrna-seq", "snrna"),
        "three-prime-single-nucleus-rna": ("3' snrna-seq", "3′ snrna-seq", "3 prime snrna-seq", "3-prime snrna-seq"),
        "single-cell-multiome": ("paired multiome", "single-cell multiome", "single cell multiome", "rna+atac", "rna-atac multiome", "multiome"),
        "cuttag": ("cut&tag", "cut and tag", "cuttag"),
        "s9-6-cuttag": ("s9.6 cut&tag", "s9.6 cuttag", "s9-6 cut&tag", "s9-6 cuttag"),
        "ip-ms": ("ip-ms", "ip–ms", "ip—ms", "ap-ms", "immunoprecipitation mass spectrometry", "affinity purification mass spectrometry"),
        "rna-secondary-structure": ("rna secondary structure", "rna 二级结构", "dot bracket", "dot-bracket"),
        "protein-secondary-structure": ("protein secondary structure", "蛋白二级结构", "dssp"),
    },
    "targets": {
        "transcript-abundance": ("transcript abundance", "gene expression", "expression change", "rna-seq", "rna and atac", "rna + atac", "转录本丰度", "差异表达"),
        "chromatin-occupancy": ("protein binding", "chromatin binding", "banp binding", "ha-banp", "occupancy", "染色质结合"),
        "chromatin-accessibility": ("chromatin accessibility", "atac", "开放染色质"),
        "r-loop": ("r-loop", "r loop", "rloop", "s9.6", "s9-6", "rna-dna hybrid", "rna dna hybrid"),
        "protein-interactome": ("protein interaction", "protein-interaction", "interactome", "ip-ms", "ip–ms", "ppi", "蛋白互作"),
        "gene-regulatory-network": ("scenic+", "scenic", "eregulon", "regulatory network", "gene regulatory network", "调控网络"),
        "rna-processing": ("rna processing", "rna-processing", "rna 加工", "rna加工"),
        "splicing": ("alternative splicing", "splicing", "splice", "junction", "可变剪接", "剪接"),
        "cell-state-dynamics": ("trajectory", "pseudotime", "rna velocity", "cellrank", "regvelo", "multivelo", "拟时序", "轨迹"),
        "rna-secondary-structure": ("rna secondary structure", "rna 二级结构", "dot bracket", "dot-bracket"),
        "protein-secondary-structure": ("protein secondary structure", "蛋白二级结构", "dssp"),
    },
    "controls": {
        "rnase-h-specificity-control": ("rnase h control", "rnase h-treated", "rnase h treated", "rnase h specificity", "rnase h", "rnase处理", "rnase h 对照"),
        "nuclease-specificity-control": ("rnase control", "rnase-treated control", "nuclease control", "核酸酶对照"),
        "igg-control": ("igg control", "isotype control", "igg 对照"),
        "input-control": ("input control", "input 对照"),
        "matched-control": ("matched control", "paired control", "匹配对照", "配对对照"),
        "biological-replicates": ("biological replicates", "biological replicate", "independent samples", "生物学重复", "独立样本"),
    },
    "normalizations": {
        "spike-in-normalization": ("spike-in normalization", "spike in normalization", "spike-in", "spike in", "internal reference normalization", "内参归一化", "外源内参"),
        "pseudobulk": ("pseudobulk", "pseudo-bulk", "sample-level aggregation", "donor-aware", "样本级聚合", "供体感知"),
        "library-size-normalization": ("library size normalization", "size factor", "tmm normalization", "cpm normalization", "文库大小归一化"),
    },
    "relations": {
        "direct-binding": ("direct binding", "direct regulation", "direct target", "direct banp regulation", "直接结合", "直接调控", "直接靶标"),
        "secondary-transcriptional-effect": ("secondary transcriptional effect", "secondary transcriptional effects", "indirect transcriptional effect", "downstream transcriptional effect", "继发转录效应", "间接转录效应"),
        "r-loop-associated-effect": ("r-loop-associated", "r loop associated", "r-loop related", "r loop related", "r-loop相关", "r-loop 相关"),
        "protein-interaction-support": ("protein-interaction support", "protein interaction support", "interaction support", "互作支持"),
        "splicing-change": ("splicing change", "splicing changes", "splice change", "剪接变化"),
        "cross-modal-concordance": ("cross-omics integration", "cross omics integration", "multi-omics integration", "integrate", "integration", "整合", "联合分析"),
        "orthogonal-validation": ("orthogonal validation", "independent validation", "正交验证", "独立验证"),
    },
}

_NEGATION = re.compile(r"(?:\b(?:no|not|without|exclude|excluding|rather than)\b|不做|不要|不使用|排除|并非|不是)", re.IGNORECASE)


@dataclass(frozen=True)
class SemanticMention:
    axis: str
    concept: str
    text: str
    start: int
    end: int
    negated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis,
            "concept": self.concept,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "negated": self.negated,
        }


@dataclass(frozen=True)
class ScientificSemanticBrief:
    objective: str
    mentions: tuple[SemanticMention, ...]
    concepts: dict[str, tuple[str, ...]]
    negated_concepts: dict[str, tuple[str, ...]]
    disambiguations: tuple[dict[str, str], ...]
    design_requirements: tuple[str, ...]
    eligibility_warnings: tuple[str, ...]

    @property
    def has_signal(self) -> bool:
        return any(self.concepts[axis] for axis in AXES)

    def to_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "mentions": [item.to_dict() for item in self.mentions],
            "concepts": {axis: list(self.concepts[axis]) for axis in AXES},
            "negated_concepts": {axis: list(self.negated_concepts[axis]) for axis in AXES},
            "disambiguations": list(self.disambiguations),
            "design_requirements": list(self.design_requirements),
            "eligibility_warnings": list(self.eligibility_warnings),
        }


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower()


def _phrase_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(_normalize(alias))
    escaped = escaped.replace(r"\ ", r"[\s_-]+")
    if re.fullmatch(r"[a-z0-9][a-z0-9 .+&'′–—_-]*", _normalize(alias)):
        return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 28):start]
    matches = list(_NEGATION.finditer(prefix))
    return bool(matches and len(prefix) - matches[-1].end() <= 16)


def _deduplicate_mentions(values: Iterable[SemanticMention]) -> tuple[SemanticMention, ...]:
    ordered = sorted(values, key=lambda item: (item.start, -(item.end - item.start), item.axis, item.concept))
    kept: list[SemanticMention] = []
    seen: set[tuple[str, str, bool]] = set()
    for item in ordered:
        identity = (item.axis, item.concept, item.negated)
        if identity in seen:
            continue
        if any(
            other.axis == item.axis
            and other.concept == item.concept
            and other.start <= item.start
            and other.end >= item.end
            for other in kept
        ):
            continue
        kept.append(item)
        seen.add(identity)
    return tuple(kept)


def parse_scientific_semantics(objective: str) -> ScientificSemanticBrief:
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("scientific objective must be nonempty")
    normalized = _normalize(objective)
    mentions: list[SemanticMention] = []
    for axis, concepts in _ALIASES.items():
        for concept, aliases in concepts.items():
            for alias in sorted(aliases, key=len, reverse=True):
                for match in _phrase_pattern(alias).finditer(normalized):
                    negated = _negated(normalized, match.start())
                    local = normalized[max(0, match.start() - 32):min(len(normalized), match.end() + 48)]
                    if concept == "spike-in-normalization" and "without treating" in local and "specificity" in local:
                        # This negates an evidentiary interpretation, not use of
                        # the normalization itself.
                        negated = False
                    if (
                        concept == "splicing"
                        and negated
                        and re.search(r"(?:do not|don't|不要|不能|不可).{0,20}(?:infer|claim|推断|认定)", local)
                        and re.search(r"(?:intronic|exonic|intron|exon|内含子|外显子)", local)
                    ):
                        # "Do not infer an AS event from intronic/exonic signal"
                        # is a claim-boundary instruction inside a requested
                        # splicing analysis, not a request to exclude the method.
                        negated = False
                    mentions.append(SemanticMention(axis, concept, objective[match.start():match.end()], match.start(), match.end(), negated))
    mentions_tuple = _deduplicate_mentions(mentions)
    positive = {
        axis: tuple(dict.fromkeys(item.concept for item in mentions_tuple if item.axis == axis and not item.negated))
        for axis in AXES
    }
    negative = {
        axis: tuple(dict.fromkeys(item.concept for item in mentions_tuple if item.axis == axis and item.negated))
        for axis in AXES
    }
    disambiguations: list[dict[str, str]] = []
    if "secondary-transcriptional-effect" in positive["relations"]:
        disambiguations.append({
            "phrase": "secondary transcriptional effect",
            "resolved_as": "downstream or indirect transcriptional consequence",
            "excluded_interpretation": "RNA or protein secondary structure",
        })
    requirements: list[str] = []
    warnings: list[str] = []
    if "s9-6-cuttag" in positive["assays"] or "r-loop" in positive["targets"]:
        requirements.extend((
            "Record the S9.6 target, antibody lot, RNase H specificity control, internal reference and normalization as separate design fields.",
            "Do not treat spike-in normalization as evidence of RNA-DNA-hybrid specificity.",
        ))
        if "nuclease-specificity-control" in positive["controls"] and "rnase-h-specificity-control" not in positive["controls"]:
            warnings.append(
                "A generic RNase control is not chemically specific enough for S9.6 interpretation; record whether the treatment was RNase H, RNase A, RNase III or another nuclease before scientific admission."
            )
    if "ip-ms" in positive["assays"]:
        requirements.extend((
            "Model or explicitly classify protein- and peptide-level missingness; an unobserved protein is not a measured zero.",
            "Use independent biological preparations as the condition-level unit and retain bait, control and contaminant evidence.",
        ))
    if "three-prime-single-nucleus-rna" in positive["assays"] or "single-nucleus-rna" in positive["assays"]:
        warnings.append(
            "Three-prime single-nucleus RNA capture is not exon-complete: intronic or exonic signal alone does not establish an alternative-splicing event without junction-aware evidence and an eligible design."
        )
    if "single-cell-multiome" in positive["assays"] and "pseudobulk" in positive["normalizations"]:
        requirements.append(
            "Aggregate immutable raw counts by reviewed cell state and biological sample; use donor, specimen or embryo rather than cells as the condition-level replicate."
        )
    return ScientificSemanticBrief(
        objective=objective,
        mentions=mentions_tuple,
        concepts=positive,
        negated_concepts=negative,
        disambiguations=tuple(disambiguations),
        design_requirements=tuple(dict.fromkeys(requirements)),
        eligibility_warnings=tuple(dict.fromkeys(warnings)),
    )


def module_semantic_concepts(module: object) -> dict[str, tuple[str, ...]]:
    contract = getattr(module, "scientific_semantics", None)
    if contract is None:
        return {axis: () for axis in AXES}
    return {axis: tuple(getattr(contract, axis)) for axis in AXES}
