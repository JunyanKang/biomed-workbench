"""Source-neutral routing from a research objective to capability steps."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

from .catalog import all_capabilities
from .models import Capability


WORKFLOW_ORDER = ("evidence", "omics", "molecular_design", "imaging", "clinical", "wetlab", "publication")
WORKFLOW_KEYWORDS = {
    "evidence": ("evidence", "literature", "pubmed", "pmc", "gene", "variant", "clinvar", "protein", "database", "文献", "证据", "数据库", "基因", "变异", "蛋白"),
    "omics": ("omics", "rna-seq", "rnaseq", "single-cell", "scrna", "expression", "enrichment", "network", "vcf", "tmb", "组学", "转录组", "单细胞", "差异", "富集", "网络", "突变负荷"),
    "molecular_design": ("crispr", "primer", "restriction", "cloning", "golden gate", "codon", "kinetics", "glycosylation", "docking", "structure", "guide", "引物", "分子", "对接", "蛋白设计", "克隆", "酶动力学", "糖基化", "组装"),
    "imaging": ("image", "microscopy", "segment", "morphology", "colocalization", "tracking", "dicom", "图像", "显微", "分割", "形态", "共定位", "追踪"),
    "clinical": ("clinical", "cohort", "survival", "biomarker", "patient", "trial", "adverse event", "case report", "临床", "队列", "生存", "标志物", "患者", "试验", "不良事件", "安全性"),
    "wetlab": ("protocol", "pcr", "qpcr", "flow cytometry", "dilution", "dose response", "growth curve", "assay", "elisa", "实验", "方案", "稀释", "剂量", "生长曲线", "流式", "免疫测定"),
    "publication": ("manuscript", "paper", "review", "citation", "figure", "patent", "response", "presentation", "nature", "论文", "审稿", "引用", "图表", "专利", "回复", "写作"),
}
INTENT_BOOSTS = {
    "gene-evidence": ("gene", "基因", "target", "靶点"),
    "variant-evidence": ("variant", "clinvar", "变异"),
    "literature-evidence": ("literature", "pubmed", "paper", "文献", "检索"),
    "crispr-design": ("crispr", "guide", "sgrna"),
    "primer-design": ("primer", "引物"),
    "differential-expression": ("differential", "差异"),
    "single-cell-qc": ("single-cell", "scrna", "单细胞"),
    "enrichment-analysis": ("enrichment", "富集", "pathway", "通路"),
    "image-segment": ("segment", "分割"),
    "image-colocalization": ("colocalization", "共定位"),
    "survival-analysis": ("survival", "生存"),
    "biomarker-performance": ("biomarker", "标志物"),
    "manuscript-audit": ("manuscript", "paper", "论文", "文章", "review"),
    "citation-audit": ("citation", "reference", "引用", "参考文献"),
    "response-matrix": ("reviewer response", "rebuttal", "回复", "答复"),
    "figure-specification": ("figure", "panel", "图表", "图"),
    "patent-disclosure-audit": ("patent", "invention", "专利", "发明"),
    "qpcr-relative-expression": ("qpcr", "delta ct", "relative expression", "相对表达", "技术重复"),
    "immunoassay-quantification": ("elisa", "immunoassay", "standard curve", "免疫测定", "标准曲线"),
    "flow-cytometry-summary": ("flow cytometry", "gating", "流式", "门控"),
    "enzyme-kinetics": ("enzyme kinetics", "michaelis", "酶动力学", "米氏"),
    "glycosylation-scan": ("glycosylation", "sequon", "糖基化"),
    "golden-gate-plan": ("golden gate", "type iis", "金门", "组装"),
    "tumor-mutation-burden": ("tmb", "tumor mutation burden", "肿瘤突变负荷", "突变负荷"),
    "adverse-event-summary": ("adverse event", "safety", "不良事件", "严重性", "安全性"),
    "reviewer-assessment": ("peer review", "reviewer", "审稿人", "评审", "主张与证据"),
}


def _contains(query: str, phrase: str) -> bool:
    return phrase.lower() in query.lower()


def infer_workflows(query: str) -> list[str]:
    matched = [workflow for workflow in WORKFLOW_ORDER if any(_contains(query, keyword) for keyword in WORKFLOW_KEYWORDS[workflow])]
    return matched or ["evidence"]


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) > 1}


def score_capability(capability: Capability, query: str, workflows: Iterable[str]) -> float:
    query_lower = query.lower()
    query_tokens = _tokens(query)
    text = f"{capability.id} {capability.title} {capability.description}".lower()
    score = 8.0 if capability.workflow in workflows else 0.0
    score += 1.5 * len(query_tokens & _tokens(text))
    score += sum(7.0 for phrase in INTENT_BOOSTS.get(capability.id, ()) if phrase.lower() in query_lower)
    if capability.access == "offline":
        score += 0.25
    return score


def route(query: str, *, per_workflow: int = 3) -> dict[str, Any]:
    if not query.strip() or not 1 <= per_workflow <= 10:
        raise ValueError("query must be nonempty and per_workflow must be 1..10")
    workflows = infer_workflows(query)
    grouped: dict[str, list[tuple[float, Capability]]] = defaultdict(list)
    for capability in all_capabilities():
        if capability.workflow in workflows:
            grouped[capability.workflow].append((score_capability(capability, query, workflows), capability))
    candidates = {}
    for workflow in workflows:
        ranked = sorted(grouped[workflow], key=lambda item: (-item[0], item[1].id))
        candidates[workflow] = [
            {"id": capability.id, "title": capability.title, "score": round(score, 3), "access": capability.access, "mutability": capability.mutability}
            for score, capability in ranked[:per_workflow]
        ]
    parallel_requested = any(term in query.lower() for term in ("parallel", "并行", "同时"))
    if len(workflows) == 1:
        plan_type = "single"
    elif parallel_requested and not ({"evidence", "publication"} & set(workflows)):
        plan_type = "parallel"
    elif parallel_requested:
        plan_type = "mixed"
    else:
        plan_type = "serial"
    steps = []
    for workflow in workflows:
        mode = "parallel" if plan_type in {"parallel", "mixed"} and workflow not in {"evidence", "publication"} else "serial"
        steps.append({"workflow": workflow, "mode": mode, "candidates": candidates[workflow]})
    return {"objective": query, "matched_workflows": workflows, "plan_type": plan_type, "steps": steps}
