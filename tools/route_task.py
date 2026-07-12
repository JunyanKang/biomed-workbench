#!/usr/bin/env python3
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

CATALOG = Path(__file__).with_name("catalog.json")

WORKFLOW_ORDER = [
    "evidence",
    "omics",
    "molecular_design",
    "imaging",
    "clinical",
    "wetlab",
    "publication",
    "runtime",
]

SERIAL_ORDER = [
    "runtime",
    "evidence",
    "omics",
    "molecular_design",
    "imaging",
    "clinical",
    "wetlab",
    "publication",
]

WORKFLOW_KEYWORDS = {
    "publication": [
        "publication",
        "paper",
        "manuscript",
        "nature",
        "cell",
        "science",
        "reviewer",
        "review",
        "citation",
        "reference",
        "patent",
        "ppt",
        "slide",
        "proposal",
        "rebuttal",
        "response",
        "figure",
        "storyline",
        "论文",
        "文章",
        "投稿",
        "审稿",
        "审稿人",
        "引用",
        "参考文献",
        "专利",
        "答复",
        "回复",
        "图表",
        "写作",
        "润色",
        "综述",
    ],
    "evidence": [
        "pubmed",
        "literature",
        "database",
        "uniprot",
        "pdb",
        "chembl",
        "pubchem",
        "variant",
        "gene",
        "protein",
        "evidence",
        "clinicaltrials",
        "gwas",
        "ensembl",
        "文献",
        "数据库",
        "证据",
        "基因",
        "蛋白",
        "变异",
        "通路",
        "检索",
        "查证",
    ],
    "omics": [
        "single-cell",
        "single cell",
        "scrna",
        "scRNA",
        "scanpy",
        "rnaseq",
        "rna-seq",
        "deseq",
        "h5ad",
        "anndata",
        "omics",
        "pathway",
        "vcf",
        "genomics",
        "transcriptome",
        "sequencing",
        "enrichment",
        "network",
        "单细胞",
        "转录组",
        "组学",
        "测序",
        "差异",
        "富集",
        "注释",
        "聚类",
        "轨迹",
        "空间转录组",
    ],
    "molecular_design": [
        "crispr",
        "primer",
        "cloning",
        "protein",
        "docking",
        "admet",
        "smiles",
        "plasmid",
        "synthetic",
        "drug",
        "molecule",
        "ligand",
        "proteinmpnn",
        "diffdock",
        "rfdiffusion",
        "boltz",
        "分子",
        "药物",
        "引物",
        "克隆",
        "质粒",
        "蛋白设计",
        "对接",
        "配体",
        "合成生物学",
    ],
    "imaging": [
        "image",
        "microscopy",
        "pathology",
        "dicom",
        "ihc",
        "phenotype",
        "morphology",
        "colocalization",
        "segmentation",
        "tracking",
        "neurophysiology",
        "图像",
        "显微",
        "病理",
        "影像",
        "免疫组化",
        "表型",
        "形态",
        "共定位",
        "分割",
        "追踪",
    ],
    "clinical": [
        "clinical",
        "patient",
        "cohort",
        "biomarker",
        "treatment",
        "survival",
        "trial",
        "case report",
        "deidentification",
        "临床",
        "患者",
        "队列",
        "生物标志物",
        "治疗",
        "生存",
        "试验",
        "病例",
        "脱敏",
    ],
    "wetlab": [
        "protocol",
        "elisa",
        "western",
        "opentrons",
        "pylabrobot",
        "benchling",
        "flow",
        "cytometry",
        "pcr",
        "colony",
        "assay",
        "实验",
        "方案",
        "协议",
        "流式",
        "细胞术",
        "蛋白印迹",
        "菌落",
        "稀释",
    ],
    "runtime": [
        "python",
        "runtime",
        "environment",
        "env",
        "install",
        "setup",
        "mcp",
        "server",
        "claude science",
        "运行",
        "环境",
        "安装",
        "配置",
        "服务",
    ],
}

SERIAL_HINTS = [
    "then",
    "after",
    "pipeline",
    "workflow",
    "end-to-end",
    "write",
    "draft",
    "publish",
    "串联",
    "流程",
    "然后",
    "最后",
    "写成",
    "整理成",
]

PARALLEL_HINTS = [
    "compare",
    "screen",
    "batch",
    "multi",
    "parallel",
    "分别",
    "多个",
    "批量",
    "并行",
    "对比",
]

TERM_ALIASES = {
    "单细胞": ["single-cell", "single cell", "scrna", "rna-seq", "h5ad", "anndata", "scanpy", "celltype"],
    "查文献": ["literature", "pubmed", "scholar", "openalex", "crossref", "europepmc"],
    "文献": ["literature", "pubmed", "scholar", "openalex", "crossref", "europepmc"],
    "证据": ["evidence", "literature", "pubmed", "database", "clinvar", "uniprot"],
    "空间转录组": ["spatial", "transcriptome", "visium", "anndata"],
    "转录组": ["rnaseq", "rna-seq", "transcriptome", "deseq"],
    "差异": ["differential", "deseq", "marker"],
    "富集": ["enrichment", "pathway"],
    "写成": ["manuscript", "writing", "nature", "publication"],
    "结果": ["result", "figure", "manuscript"],
    "审稿": ["reviewer", "review", "critique"],
    "专利": ["patent", "claim"],
    "引物": ["primer"],
    "质粒": ["plasmid", "cloning"],
    "对接": ["docking", "ligand"],
    "图像": ["image", "segmentation", "morphology"],
    "临床": ["clinical", "cohort", "patient"],
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "use",
    "with",
    "analysis",
    "analyze",
    "help",
}

INTENT_RULES = [
    {
        "triggers": ["reviewer", "review", "peer review", "审稿", "审稿人"],
        "excludes": ["literature review", "systematic review", "scoping review"],
        "boosts": {"publication_reviewer": 72},
    },
    {
        "triggers": ["verify every citation", "verify citation", "citation", "reference", "引用", "参考文献", "查证"],
        "boosts": {
            "publication_ref_verifier": 60,
            "publication_citation": 34,
            "nature_citation": 30,
        },
    },
    {
        "triggers": ["crispr", "sgrna", "guide rna", "基因编辑"],
        "boosts": {
            "design_crispr": 40,
            "analyze_crispr_genome_editing": 24,
            "design_knockout_sgrna": 20,
        },
    },
    {
        "triggers": ["rna-seq", "rnaseq", "deseq", "bulk rna", "转录组", "差异表达"],
        "boosts": {"run_deseq2_analysis": 40, "qc_analysis": 22},
    },
    {
        "triggers": ["protocol", "实验方案", "实验协议", "方案", "协议"],
        "boosts": {"search_protocols": 40, "get_protocol_details": 34, "list_local_protocols": 22},
    },
    {
        "triggers": ["nature", "manuscript", "paper", "论文", "文章", "写成"],
        "boosts": {"publication_writing": 34, "publication_polishing": 24},
    },
    {
        "triggers": ["literature", "pubmed", "文献", "证据", "检索"],
        "boosts": {"search_pubmed": 32, "search_europepmc": 26, "search_openalex": 22},
    },
    {
        "triggers": ["environment", "runtime", "环境", "运行状态"],
        "boosts": {"runtime_status": 32, "python_env": 20, "r_env": 18},
    },
]

CODE_LIKE_DESCRIPTION = re.compile(r"\b(import\s+\w+|from\s+\w+\s+import|def\s+[a-z_]\w*\s*\()")


def load_catalog():
    return json.loads(CATALOG.read_text())


def compact(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def entry_text(entry):
    fields = [
        entry.get("id", ""),
        entry.get("workflow", ""),
        entry.get("kind", ""),
        entry.get("name", ""),
        entry.get("description", ""),
        entry.get("source", ""),
        entry.get("path", ""),
        entry.get("function", ""),
        entry.get("domain", ""),
    ]
    return " ".join(compact(v) for v in fields).lower()


def query_terms(query):
    lowered = query.lower()
    terms = set(re.findall(r"[a-z0-9][a-z0-9_+.-]*", lowered))
    for words in WORKFLOW_KEYWORDS.values():
        for word in words:
            if word.lower() in lowered:
                terms.add(word.lower())
    for word, aliases in TERM_ALIASES.items():
        if word.lower() in lowered:
            terms.update(alias.lower() for alias in aliases)
    return sorted((term for term in terms if term not in STOPWORDS and len(term) > 1), key=len, reverse=True)


def infer_workflows(query, forced):
    if forced:
        return [w for w in WORKFLOW_ORDER if w in forced]

    lowered = query.lower()
    scores = {}
    for workflow, keywords in WORKFLOW_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            key = keyword.lower()
            if key in lowered:
                score += 3 if " " in key or len(key) > 3 else 1
        if score:
            scores[workflow] = score

    if "nature" in lowered and any(k in lowered for k in ["result", "结果", "paper", "论文", "写成"]):
        scores["publication"] = scores.get("publication", 0) + 4
    if "single" in lowered and "cell" in lowered:
        scores["omics"] = scores.get("omics", 0) + 4

    ranked = sorted(scores.items(), key=lambda item: (-item[1], WORKFLOW_ORDER.index(item[0])))
    return [workflow for workflow, _ in ranked]


def intent_boosts(query):
    lowered = query.lower()
    boosts = defaultdict(int)
    for rule in INTENT_RULES:
        excluded = any(term in lowered for term in rule.get("excludes", []))
        if not excluded and any(trigger in lowered for trigger in rule["triggers"]):
            for tool_id, value in rule["boosts"].items():
                boosts[tool_id] += value
    return boosts


def normalized_field(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", compact(value).lower())


def score_one(entry, terms, workflows, boosts):
    identity = normalized_field(" ".join([entry.get("id", ""), entry.get("name", "")]))
    description = normalized_field(entry.get("description", ""))
    metadata = normalized_field(" ".join([entry.get("domain", ""), entry.get("path", "")]))
    lexical_score = 0
    for term in terms:
        normalized_term = normalized_field(term)
        if not normalized_term:
            continue
        if normalized_term in identity:
            lexical_score += 8
        elif normalized_term in description:
            lexical_score += 4
        elif normalized_term in metadata:
            lexical_score += 2

    intent_score = boosts.get(entry.get("id"), 0)
    if not lexical_score and not intent_score:
        return 0

    score = lexical_score + intent_score
    if entry.get("workflow") in workflows:
        score += 4
    if entry.get("run_policy") == "direct":
        score += 1
    return score


def score_entries(entries, query, workflows, limit):
    terms = query_terms(query)
    boosts = intent_boosts(query)
    scored = []
    for entry in entries:
        score = score_one(entry, terms, workflows, boosts)
        if score:
            scored.append((score, entry))

    scored.sort(key=lambda item: (-item[0], item[1].get("workflow", ""), item[1].get("id", "")))
    if not workflows:
        return [summarize_entry(entry, score) for score, entry in scored[:limit]]

    selected = []
    seen = set()
    eligible_ids = set()
    per_workflow = max(2, limit // max(1, len(workflows)))
    by_workflow = defaultdict(list)
    for score, entry in scored:
        by_workflow[entry.get("workflow")].append((score, entry))

    for workflow in workflows:
        workflow_scores = by_workflow.get(workflow, [])
        best_score = workflow_scores[0][0] if workflow_scores else 0
        margin = 30 if best_score >= 50 else 15 if best_score >= 30 else 3
        confident = [item for item in workflow_scores if item[0] >= max(8, best_score - margin)]
        eligible_ids.update(entry.get("id") for _, entry in confident)
        for score, entry in confident[:per_workflow]:
            selected.append((score, entry))
            seen.add(entry.get("id"))

    for score, entry in scored:
        if len(selected) >= limit:
            break
        if workflows and entry.get("id") not in eligible_ids:
            continue
        if entry.get("id") in seen:
            continue
        selected.append((score, entry))
        seen.add(entry.get("id"))

    return [summarize_entry(entry, score) for score, entry in selected[:limit]]


def summarize_entry(entry, score):
    return {
        "id": entry.get("id"),
        "workflow": entry.get("workflow"),
        "kind": entry.get("kind"),
        "name": entry.get("name"),
        "description": human_description(entry),
        "run_policy": entry.get("run_policy"),
        "path": entry.get("path"),
        "score": score,
    }


def human_description(entry):
    description = compact(entry.get("description"))
    if not description or description == ">-" or CODE_LIKE_DESCRIPTION.search(description):
        name = compact(entry.get("name") or entry.get("id")).replace("_", " ")
        kind = compact(entry.get("kind", "capability")).replace("_", " ")
        workflow = compact(entry.get("workflow", "biomedical")).replace("_", " ")
        return f"{name}: reusable {kind} for the {workflow} workflow."
    return description[:220]


def plan_type_for(query, workflows, candidates):
    if len(workflows) <= 1:
        return "single"

    lowered = query.lower()
    has_serial_hint = any(hint in lowered for hint in SERIAL_HINTS)
    has_parallel_hint = any(hint in lowered for hint in PARALLEL_HINTS)
    has_publication_sink = "publication" in workflows and any(w != "publication" for w in workflows)
    has_runtime_setup = "runtime" in workflows and any(w != "runtime" for w in workflows)

    if has_parallel_hint and not has_publication_sink and not has_serial_hint:
        return "parallel"
    if has_publication_sink and has_parallel_hint:
        return "mixed"
    if has_publication_sink or has_runtime_setup or has_serial_hint:
        return "serial"

    direct_workflows = defaultdict(int)
    for candidate in candidates:
        if candidate.get("run_policy") == "direct":
            direct_workflows[candidate["workflow"]] += 1
    if len(direct_workflows) > 1:
        return "parallel"
    return "mixed"


def candidate_ids_for(candidates, workflow, max_ids=4):
    ids = []
    for candidate in candidates:
        if candidate.get("workflow") == workflow and candidate.get("id") not in ids:
            ids.append(candidate.get("id"))
        if len(ids) >= max_ids:
            break
    return ids


def build_steps(query, workflows, candidates, plan_type):
    ordered = [w for w in SERIAL_ORDER if w in workflows]
    if not ordered and candidates:
        ordered = []
        for candidate in candidates:
            workflow = candidate.get("workflow")
            if workflow and workflow not in ordered:
                ordered.append(workflow)

    if not ordered:
        return [
            {
                "step": "Clarify biomedical objective and search the unified catalog.",
                "workflow": "evidence",
                "tool_ids": [],
                "mode": "single",
                "rationale": "No workflow keyword was strong enough; start from broad evidence/tool discovery.",
            }
        ]

    steps = []
    for workflow in ordered:
        mode = "single"
        if plan_type == "parallel" and len(ordered) > 1:
            mode = "parallel"
        elif plan_type == "mixed" and workflow not in {"publication", "runtime"}:
            mode = "parallel"
        elif plan_type in {"serial", "mixed"}:
            mode = "serial"

        rationale = {
            "runtime": "Check or prepare the local environment before dependent work.",
            "evidence": "Ground the task in literature, database, and connector evidence.",
            "omics": "Analyze biological datasets, genes, variants, pathways, or single-cell data.",
            "molecular_design": "Handle molecule, protein, CRISPR, primer, docking, or synthetic biology design.",
            "imaging": "Process images, microscopy, pathology, DICOM, morphology, or phenotype data.",
            "clinical": "Prepare cohort, biomarker, survival, treatment, or clinical translation outputs.",
            "wetlab": "Prepare protocol, assay, flow cytometry, automation, or bench-adjacent calculations.",
            "publication": "Synthesize results into manuscript, review, citation, patent, PPT, or Nature-style output.",
        }.get(workflow, "Use the matched workflow tools.")

        steps.append(
            {
                "step": f"Use {workflow} workflow.",
                "workflow": workflow,
                "tool_ids": candidate_ids_for(candidates, workflow),
                "mode": mode,
                "rationale": rationale,
            }
        )

    if plan_type == "mixed" and steps:
        steps[-1]["mode"] = "serial"
    return steps


def main():
    parser = argparse.ArgumentParser(description="Route a biomedical task through the unified workbench.")
    parser.add_argument("query", nargs="+", help="User task or search query.")
    parser.add_argument("--workflow", action="append", choices=WORKFLOW_ORDER, help="Force one or more workflows.")
    parser.add_argument("--limit", type=int, default=12, help="Maximum candidate tools to return.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON. Default is pretty when stdout is a terminal.")
    args = parser.parse_args()

    query = " ".join(args.query).strip()
    catalog = load_catalog()
    entries = catalog.get("entries", [])
    workflows = infer_workflows(query, args.workflow or [])
    if not workflows:
        workflows = []

    candidates = score_entries(entries, query, workflows, args.limit)
    if not workflows:
        for candidate in candidates:
            workflow = candidate.get("workflow")
            if workflow and workflow not in workflows:
                workflows.append(workflow)
            if len(workflows) >= 3:
                break

    plan_type = plan_type_for(query, workflows, candidates)
    result = {
        "query": query,
        "matched_workflows": workflows,
        "plan_type": plan_type,
        "steps": build_steps(query, workflows, candidates, plan_type),
        "candidate_tools": candidates,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
