"""Deterministic, evidence-bounded proposal writing and DOCX delivery gates."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


_NSFC_PROFILE_PATH = Path(__file__).resolve().parents[1] / "proposal_profiles" / "nsfc-2026.json"
NSFC_PROFILE_VERSION = "2026.4"
NSFC_OFFICIAL_SOURCES = (
    "https://www.nsfc.gov.cn/p1/2961/2962/3642/sqs.html",
    "https://www.nsfc.gov.cn/p1/2961/2962/4089/yjsx.html",
    "https://www.nsfc.gov.cn/p1/2961/2962/2967/sqsj.html",
)
NSFC_RESEARCH_ATTRIBUTES = {
    "自由探索类基础研究": "选题源于科研人员好奇心或创新性学术灵感，且不以满足现阶段应用需求为目的。",
    "目标导向类基础研究": "以经济社会发展需要或国家需求为牵引。",
}
NSFC_LIFE_SCIENCE_PROGRAMS_REQUIRING_SECOND_LEVEL_CODE = {
    "general",
    "young-c",
    "regional",
}

_SECTION_ALIASES = {
    "abstract_cn": {"中文摘要", "摘要"},
    "abstract_en": {"英文摘要", "abstract"},
    "rationale": {"立项依据", "项目的立项依据"},
    "research_status": {"国内外研究现状", "研究现状", "国内外现状及发展动态"},
    "scientific_significance": {"科学意义", "研究意义"},
    "scientific_question": {"科学问题", "拟解决的关键科学问题"},
    "central_hypothesis": {"科学假说", "中心假说"},
    "research_content": {"研究内容", "研究内容、研究目标及拟解决的关键科学问题"},
    "research_plan": {"研究方案", "拟采取的研究方案及可行性分析"},
    "technical_route": {"技术路线", "研究技术路线"},
    "innovation": {"特色与创新之处", "创新点", "项目的特色与创新之处"},
    "annual_plan": {"年度研究计划", "年度计划"},
    "preliminary": {"研究基础", "工作基础", "与本项目有关的研究工作积累和已取得的研究工作成绩"},
    "academic_achievements": {"主要学术成绩", "代表性学术成绩", "学术贡献"},
    "future_research": {"拟开展的研究工作", "未来研究计划", "研究工作设想"},
    "references": {"参考文献", "主要参考文献"},
}
_SECTION_OPERATION_TERMS = re.compile(
    r"(?:拟采用|拟通过|本项目将|计划开展|将检测|将构建|将观察|预期获得|采用.+?方法)",
    re.IGNORECASE,
)
_PRELIMINARY_DATA_TERMS = re.compile(
    r"(?:本课题组|本团队|前期研究|预实验|初步结果|我们观察到|申请人前期|本研究已)",
    re.IGNORECASE,
)
_NUMERIC_CITATION = re.compile(r"\[(\s*\d+(?:\s*[-–,，;；]\s*\d+)*\s*)\]")
_REFERENCE_LABEL = re.compile(r"^\s*\[?(\d+)\]?[.、]?\s+")
_INTERNAL_GOVERNANCE_TERMS = {
    "门控": "判定标准",
    "证据链": "证据依据",
    "状态机": "结果状态管理规则",
    "promotion gate": "结论升级条件",
    "artifact": "研究材料或结果文件",
    "registry": "登记信息",
}
_UNNATURAL_CHINESE = {
    "递进判定": "逐步检验",
    "底物层级": "候选底物的证据强度",
    "第一条边界": "首先需要区分",
    "来源归因": "证据来源",
    "同一分析框架": "统一的分析方法",
    "为分子起点": "作为候选分子线索",
    "时间能力": "发育时期相关信息",
    "疾病生物学意义": "与疾病发生发展的潜在联系",
    "分开判定": "分别检验",
    "这些信息仍属于候选形成依据": "这些结果仅用于筛选候选分子",
    "层级化证据": "不同强度的证据",
    "判定边界": "结论适用范围",
    "执行闭环": "从分析到结果复核的完整过程",
}
_MECHANISM_STEPS = (
    "coexpression",
    "spatial_colocalization",
    "physical_interaction",
    "site_specific_modification",
    "catalytic_dependency",
    "assembly_change",
    "phenotype_link",
    "rescue",
)
_CLAIM_LEVELS = {"candidate": 0, "association": 1, "function": 2, "substrate": 3, "mechanism": 4, "causal": 5}
_PROPOSAL_EVIDENCE_STATUSES = {
    "field-consensus",
    "direct-study",
    "clinical-genetics",
    "database-phenotype",
    "preliminary-data",
    "public-reanalysis",
    "biological-inference",
    "candidate",
    "hypothesis",
    "to-be-tested",
}
_PROPOSAL_EVIDENCE_UPSTREAM_MODULES = (
    "literature-evidence",
    "literature-landscape-audit",
    "citation-record-resolution",
    "citation-resolution-adjudication",
    "claim-evidence-integrity-audit",
)
_PROPOSAL_POST_DRAFT_REVIEW_MODULES = (
    "assertion-citation-coverage-audit",
    "citation-audit",
    "source-freshness-audit",
    "nsfc-proposal-semantic-audit",
    "biomedical-terminology-and-nomenclature-audit",
    "mechanism-claim-promotion-gate",
    "academic-prose-revision-audit",
    "docx-citation-delivery-audit",
)
_PROPOSAL_FIGURE_ROLES = {
    "rationale-evidence-synthesis": {
        "section": "rationale",
        "purpose": "把领域共识、直接证据、相互矛盾的解释和尚未解决的问题压缩为一幅可核查的证据综合图。",
        "required_node_kinds": {"established", "gap", "question"},
        "required_evidence_roles": {"field-consensus", "direct-support", "gap-defining"},
        "composition": "从生物学对象和尺度出发，沿已有认识、关键矛盾、知识缺口到本项目研究入口形成连续视觉叙事。",
        "forbidden": "不得用无来源的因果箭头、装饰性器官或分子图标替代证据，不得把拟开展实验或预期结果画成已经证实的事实。",
    },
    "scientific-hypothesis": {
        "section": "central_hypothesis",
        "purpose": "将已建立证据、申请人前期结果、生物学推断、中心假说、替代解释和可否定观察清楚分层。",
        "required_node_kinds": {"established", "preliminary", "inference", "hypothesis", "falsifier"},
        "required_evidence_roles": set(),
        "composition": "以组织或细胞背景为主体，在空间上连接分子事件、细胞过程和表型层级，并把待检验环节与已知事实用不同视觉语法区分。",
        "forbidden": "不得把候选机制画成确定通路，不得用实线、确定性措辞或同一颜色把假说与已证实事实混为一谈。",
    },
    "research-workflow": {
        "section": "research_plan",
        "purpose": "说明研究问题如何被实验设计、关键对照、读出和分支决策逐步检验。",
        "required_node_kinds": {"question", "model", "method", "control", "readout", "decision"},
        "required_evidence_roles": set(),
        "composition": "以研究目标为纵向主线，横向呈现实验层级、模型、方法、关键对照、定量读出与结果分支；突出科学判定而不是罗列技术名称。",
        "forbidden": "不得把方法清单当作科学逻辑，不得省略实验单位、关键对照和不同结果对应的下一步。",
    },
    "technical-route": {
        "section": "technical_route",
        "purpose": "把研究目标之间的依赖、每一步的输入输出、阶段成果和调整路径呈现为可执行路线。",
        "required_node_kinds": {"aim", "input", "method", "readout", "decision", "milestone"},
        "required_evidence_roles": set(),
        "composition": "采用分层或泳道式结构，把动物、组织、细胞、分子和数据分析放在正确尺度；用少量连接线表达依赖，用视觉分组表达并行任务。",
        "forbidden": "不得形成密集小字矩阵，不得让每个框具有相同视觉权重，不得用装饰性箭头制造并不存在的先后或因果关系。",
    },
    "preliminary-foundation": {
        "section": "preliminary",
        "purpose": "用申请团队真实产生的定量结果、图像和实验材料证明研究入口、模型与关键技术可行。",
        "required_node_kinds": {"preliminary", "readout", "feasibility"},
        "required_evidence_roles": set(),
        "composition": "以真实数据 panel 为主体，必要的机制或实验示意只作辅助；每个 panel 都连接样本、统计单位、来源数据和允许结论。",
        "forbidden": "不得用生成图替代显微图、印迹、测序结果或统计图，不得把文献图写成申请人的前期结果。",
    },
    "achievement-lineage": {
        "section": "academic_achievements",
        "purpose": "围绕持续研究主线组织代表性贡献、申请人作用、相互衔接的知识增量和下一步研究跃迁。",
        "required_node_kinds": {"achievement", "knowledge-advance", "future-question"},
        "required_evidence_roles": set(),
        "composition": "以少数代表性贡献为视觉锚点，展示它们如何共同形成持续研究方向，并自然收束到未来科学问题。",
        "forbidden": "不得堆砌论文封面、影响因子或荣誉，不得把共同作者成果整体归为申请人个人贡献。",
    },
}
_PROPOSAL_FIGURE_NODE_KINDS = {
    "established", "preliminary", "inference", "hypothesis", "falsifier", "gap", "question",
    "model", "method", "control", "readout", "decision", "aim", "input", "milestone",
    "feasibility", "achievement", "knowledge-advance", "future-question",
}
_PROPOSAL_FIGURE_EVIDENCE_STYLES = {
    "established": {"fill": "desaturated blue", "border": "solid", "label": "已有研究证据"},
    "preliminary": {"fill": "muted amber", "border": "solid", "label": "申请人前期结果"},
    "inference": {"fill": "light neutral grey", "border": "dashed", "label": "科学推断"},
    "hypothesis": {"fill": "restrained coral", "border": "dashed", "label": "待检验假说"},
    "falsifier": {"fill": "white", "border": "double or dark dashed", "label": "可否定观察"},
    "gap": {"fill": "white", "border": "dark dotted", "label": "尚未解决的问题"},
}
_PROPOSAL_PROGRAM_FIGURE_EMPHASIS = {
    "young-c": {
        "story": "青年 C 围绕一个边界清楚且可由申请人独立完成的科学问题，压缩为直接证据、中心假说、两到三个递进研究目标和必要前期基础。",
        "visual_priority": "用一幅简洁而具体的研究方案图展示问题、机制验证与生理意义，突出关键模型和判别性实验，避免扩展为多条平行研究主线。",
        "avoid": "避免以宏大领域全景、论文履历或过多技术平台稀释青年 C 项目的独立问题。",
    },
    "young-b": {
        "story": "青年 B 先用代表性贡献及申请人作用建立持续研究主线，再从既有知识增量推出尚未解决的前沿问题和下一阶段研究跃迁。",
        "visual_priority": "成果总览图突出少数相互衔接的原创贡献；拟开展工作图必须把已完成成果与未来问题视觉分区，并说明为什么下一步由申请人的研究积累自然导出。",
        "avoid": "避免把论文封面、期刊名或成果数量当作学术贡献，也避免把未来计划画成既有成果的简单延长。",
    },
    "young-a": {
        "story": "青年 A 围绕持续原创贡献、国际前沿位置和未来引领方向建立从既有学术体系到新领域开拓的连续叙事。",
        "visual_priority": "强调申请人建立的概念体系、领域影响和未来方向之间的结构关系，图形层级应体现引领性而不是项目任务清单。",
        "avoid": "避免用青年 C 式单一技术路线替代学术贡献与未来方向的整体论证。",
    },
    "general": {
        "story": "面上项目从领域共识与相互冲突的证据形成科学张力，提出中心假说，再以相互依赖的研究内容、判别性实验和充分前期基础证明创新性与可行性。",
        "visual_priority": "立项依据图负责压缩背景与缺口，研究设想图连接研究对象、多尺度机制和知识增量，技术路线图呈现各目标输入输出和阶段决策，前期数据图证明研究入口。",
        "avoid": "避免只有背景综述或方法矩阵，也避免把丰富的前期结果直接升级为尚未验证的因果机制。",
    },
    "regional": {
        "story": "以科学问题为主线，同时证明现有条件能够完成关键研究并形成地区科研人才与研究基础的持续积累。",
        "visual_priority": "科学机制和实验判定保持主视觉，地区条件只在可行性层作为支撑。",
        "avoid": "避免把地域意义、平台清单或人才培养替代科学问题。",
    },
    "key": {
        "story": "围绕有限但具有突破性的目标组织系统研究，突出强前期基础、必要交叉和可实现的关键知识跃迁。",
        "visual_priority": "用少量主目标与集成节点表达系统性，明确各技术分支为何不可替代。",
        "avoid": "避免方法堆叠、平均分配视觉权重或缺少最终集成判断。",
    },
    "major": {
        "story": "从统一的重大科学问题出发，展示项目与课题分解、课题间依赖和最终综合集成。",
        "visual_priority": "总图优先呈现共同科学问题、课题接口、共享资源和集成里程碑，而不是逐课题方法细节。",
        "avoid": "避免把多个互不依赖的课题并列拼接成项目。",
    },
}
_PROPOSAL_DATABASE_SOURCE_MODULES = {
    "alphafold-structure-evidence", "archs4-expression-evidence", "cbioportal-gene-copy-number-evidence",
    "cbioportal-gene-mutation-evidence", "cbioportal-study-evidence", "clinical-trial-evidence",
    "dbsnp-rsid-evidence", "ensembl-gene-evidence", "gene-evidence", "gene-ortholog-evidence",
    "gnomad-gene-constraint-evidence", "hpo-term-evidence", "opentargets-target-disease-evidence",
    "preprint-evidence", "protein-interaction-network-evidence", "quickgo-term-evidence",
    "reactome-overrepresentation-evidence", "reactome-pathway-evidence", "structure-evidence",
    "uniprot-protein-evidence", "variant-evidence",
}
_SECTION_WRITING_MOVES = {
    "rationale": ["界定研究对象", "综合领域共识", "提出关键矛盾或知识缺口", "说明缺口为何重要", "收束到中心科学问题与研究入口"],
    "research_status": ["按科学问题组织直接证据", "比较一致与冲突结果", "指出现有证据不能回答的关键问题"],
    "scientific_significance": ["说明将改变的现有认识", "解释对相关领域的具体推动", "避免以一般背景替代科学价值"],
    "scientific_question": ["用可检验命题表述中心问题", "明确主要替代解释", "给出能够区分解释的关键观测"],
    "central_hypothesis": ["陈述机制方向", "标明证据基础", "保留尚待验证的环节", "给出可被否定的结果"],
    "research_content": ["对应一个科学目标", "声明待检验假设", "安排关键实验与对照", "指定判别性读出", "解释不同结果如何改变结论"],
    "research_plan": ["说明实验对象与分组", "给出关键方法和参数", "声明统计单位与质量控制", "说明风险与替代方案"],
    "technical_route": ["按科学依赖关系排列步骤", "标明每一步输入输出", "设置继续、调整或停止的决策节点"],
    "preliminary": ["陈述本团队已经获得的结果", "说明其对本项目的直接支持", "界定仍未解决的问题", "证明关键技术与材料可用"],
    "innovation": ["指出相对现有认识的具体变化", "说明为何由本项目的设计才能实现", "避免以方法数量或首次使用替代创新性"],
    "annual_plan": ["把年度任务对应到研究目标", "声明可检查的里程碑", "给出年度末科学决策输出"],
    "academic_achievements": ["选择代表性贡献", "说明申请人的直接贡献", "建立持续研究主线", "界定其在领域中的位置"],
    "future_research": ["从既有贡献推出下一科学问题", "说明预期跃迁", "给出可执行研究路径", "体现独立性或引领性"],
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_nsfc_profile() -> dict[str, Any]:
    try:
        profile = json.loads(_NSFC_PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("the versioned NSFC profile is missing or invalid") from exc
    if profile.get("profile_version") != NSFC_PROFILE_VERSION:
        raise RuntimeError("the installed NSFC profile and capability code are out of sync")
    return profile


def canonical_agency(agency: str) -> str:
    """Resolve funding agencies by exact aliases; NSFC must never inherit NSF rules."""
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(agency).strip().lower())
    aliases = {
        "nsfc": {"nsfc", "国家自然科学基金", "国家自然科学基金委员会", "国自然"},
        "nsf": {"nsf", "national science foundation", "usnsf", "美国国家科学基金会"},
        "nih": {"nih", "national institutes of health", "美国国立卫生研究院"},
    }
    for canonical, values in aliases.items():
        if normalized in {re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", item.lower()) for item in values}:
            return canonical
    return normalized or "unknown"


def _normalize_section_name(value: str) -> str:
    normalized = re.sub(r"[\s：:、，,。.;；()（）\d一二三四五六七八九十]+", "", value).lower()
    for section_id, aliases in _SECTION_ALIASES.items():
        if any(re.sub(r"[\s：:、，,。.;；()（）\d一二三四五六七八九十]+", "", alias).lower() in normalized for alias in aliases):
            return section_id
    return "unclassified"


def _finding(code: str, severity: str, location: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "location": location, "message": message, **details}


def _review_proposal_evidence_foundation(
    foundation: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require observed literature, citation and database work before drafting."""
    search_plan = dict(foundation.get("search_plan") or {})
    sources = {str(value).strip() for value in search_plan.get("sources", []) if str(value).strip()}
    if (
        not str(search_plan.get("objective", "")).strip()
        or not search_plan.get("queries")
        or len(sources) < 2
        or not search_plan.get("date_window")
        or not search_plan.get("inclusion_criteria")
        or not search_plan.get("exclusion_criteria")
    ):
        findings.append(_finding(
            "proposal-literature-search-plan-incomplete", "major", "evidence_foundation.search_plan",
            "项目书文献检索必须说明目标、检索式、至少两个适当来源、时间范围及纳入排除标准。",
        ))

    receipt_by_module: dict[str, dict[str, Any]] = {}
    for index, receipt in enumerate(foundation.get("upstream_receipts", []), start=1):
        module_id = str(receipt.get("module_id", "")).strip()
        digest = str(receipt.get("output_digest", "")).lower()
        status = str(receipt.get("status", "")).lower()
        if not module_id or status not in {"completed", "passed"} or not re.fullmatch(r"[0-9a-f]{64}", digest):
            findings.append(_finding(
                "proposal-upstream-receipt-invalid", "major", f"evidence_foundation.upstream_receipts.{index}",
                "上游能力记录必须包含模块、成功状态和实际输出校验值。",
            ))
            continue
        receipt_by_module[module_id] = receipt
    missing_modules = sorted(set(_PROPOSAL_EVIDENCE_UPSTREAM_MODULES) - set(receipt_by_module))
    if missing_modules:
        findings.append(_finding(
            "proposal-evidence-workflow-incomplete", "major", "evidence_foundation.upstream_receipts",
            "项目书正文开始前尚未完成必需的文献检索、文献格局、引用身份和主张—证据复核。",
            missing_module_ids=missing_modules,
        ))

    literature_records = list(foundation.get("literature_records") or [])
    if not literature_records:
        findings.append(_finding(
            "proposal-literature-records-missing", "major", "evidence_foundation.literature_records",
            "没有可进入项目书论证的已审阅文献记录。",
        ))
    central_roles = {"field-consensus", "direct-support", "conflicting", "gap-defining"}
    supported_claim_ids: set[str] = set()
    for index, row in enumerate(literature_records, start=1):
        location = f"evidence_foundation.literature_records.{index}"
        required = (
            "id", "stable_id", "title", "source", "study_design", "source_level", "evidence_role",
            "evidence_relation", "claim_ids", "citation_identity_status", "content_review_status", "retraction_status",
        )
        missing = [field for field in required if not row.get(field)]
        if missing:
            findings.append(_finding("proposal-literature-record-incomplete", "major", location, "文献记录缺少项目书证据判断所需字段。", missing=missing))
            continue
        claim_ids = {str(value) for value in row.get("claim_ids", []) if str(value)}
        supported_claim_ids.update(claim_ids)
        unknown_claims = sorted(claim_ids - set(claims_by_id))
        if unknown_claims:
            findings.append(_finding("proposal-literature-claim-unregistered", "major", location, "文献记录连接了未登记的项目书主张。", claim_ids=unknown_claims))
        if row.get("citation_identity_status") != "verified_match":
            findings.append(_finding("proposal-citation-identity-unresolved", "major", location, "引用身份尚未完成多来源核验。"))
        if row.get("evidence_role") in central_roles and row.get("content_review_status") not in {"full-text-reviewed", "original-source-reviewed"}:
            findings.append(_finding("proposal-central-source-not-read", "major", location, "支撑共识、直接证据、冲突或研究空白的核心文献必须审阅原文内容。"))
        if row.get("retraction_status") not in {"not-retracted", "corrected-reviewed"}:
            findings.append(_finding("proposal-source-status-unresolved", "major", location, "文献的撤稿或更正状态尚未明确。"))

    database_records = list(foundation.get("database_records") or [])
    database_claim_ids: set[str] = set()
    for index, row in enumerate(database_records, start=1):
        location = f"evidence_foundation.database_records.{index}"
        module_id = str(row.get("module_id", ""))
        claim_ids = {str(value) for value in row.get("claim_ids", []) if str(value)}
        database_claim_ids.update(claim_ids)
        if (
            module_id not in _PROPOSAL_DATABASE_SOURCE_MODULES
            or not row.get("record_id")
            or not row.get("source_version")
            or not row.get("accessed_at")
            or not claim_ids
            or row.get("evidence_relation") not in {"supports", "weakens", "refutes", "context"}
        ):
            findings.append(_finding("proposal-database-record-incomplete", "major", location, "公共数据库记录必须绑定具体适配器、记录、版本、访问日期、主张及证据关系。"))
        if module_id and module_id not in receipt_by_module:
            findings.append(_finding("proposal-database-module-not-run", "major", location, "登记了公共数据库证据，但没有对应模块的实际输出记录。", module_id=module_id))
        unknown_claims = sorted(claim_ids - set(claims_by_id))
        if unknown_claims:
            findings.append(_finding("proposal-database-claim-unregistered", "major", location, "数据库记录连接了未登记的项目书主张。", claim_ids=unknown_claims))

    database_required_claims = {
        claim_id for claim_id, row in claims_by_id.items()
        if row.get("status") in {"database-phenotype", "clinical-genetics"}
    }
    missing_database_claims = sorted(database_required_claims - database_claim_ids)
    if missing_database_claims:
        findings.append(_finding(
            "proposal-database-evidence-unbound", "major", "evidence_foundation.database_records",
            "数据库或人类遗传学主张没有绑定实际公共数据库记录。", claim_ids=missing_database_claims,
        ))

    external_claims = {
        claim_id for claim_id, row in claims_by_id.items()
        if row.get("status") in {"field-consensus", "direct-study", "clinical-genetics", "database-phenotype"}
    }
    unbound_external_claims = sorted(external_claims - supported_claim_ids - database_claim_ids)
    if unbound_external_claims:
        findings.append(_finding(
            "proposal-external-claim-unreviewed", "major", "evidence_foundation",
            "外部事实性主张没有连接到已审阅文献或数据库记录。", claim_ids=unbound_external_claims,
        ))

    gap = dict(foundation.get("research_gap") or {})
    missing_gap = [
        field for field in ("statement", "coverage_basis", "conflicting_evidence", "why_existing_work_is_insufficient", "testable_consequence")
        if not gap.get(field)
    ]
    if missing_gap:
        findings.append(_finding(
            "proposal-research-gap-unsupported", "major", "evidence_foundation.research_gap",
            "研究空白必须由检索覆盖、冲突证据、现有研究不足和可检验后果共同界定。", missing=missing_gap,
        ))

    return {
        "search_sources": sorted(sources),
        "query_count": len(search_plan.get("queries", [])),
        "literature_record_count": len(literature_records),
        "database_record_count": len(database_records),
        "upstream_module_ids": sorted(receipt_by_module),
        "required_pre_draft_modules": list(_PROPOSAL_EVIDENCE_UPSTREAM_MODULES),
        "required_post_draft_modules": list(_PROPOSAL_POST_DRAFT_REVIEW_MODULES),
        "research_gap": gap,
    }


def prepare_nsfc_proposal_drafting(
    guideline_year: int,
    program_type: str,
    mode: str,
    scope: dict[str, Any],
    research_canon: list[dict[str, Any]],
    evidence_table: list[dict[str, Any]],
    argument_map: dict[str, Any],
    section_contracts: list[dict[str, Any]],
    aims: list[dict[str, Any]],
    evidence_foundation: dict[str, Any],
    official_template: dict[str, Any] | None = None,
    annual_plan: list[dict[str, Any]] | None = None,
    existing_sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prepare a source-bound NSFC drafting package that Codex must turn into prose.

    The returned package is an internal writing brief, not the user-facing
    deliverable. Its delivery contract explicitly requires drafted or revised
    proposal text after the scientific foundation is ready.
    """
    profile = _load_nsfc_profile()
    if guideline_year != profile["valid_for_application_year"]:
        raise ValueError("the requested NSFC guideline year is not installed")
    if program_type not in profile["programs"]:
        raise ValueError("program_type is unsupported")
    if mode not in {"compose", "revise", "hybrid"}:
        raise ValueError("mode must be compose, revise, or hybrid")
    if not isinstance(scope, dict) or not isinstance(argument_map, dict):
        raise ValueError("scope and argument_map must be objects")

    findings: list[dict[str, Any]] = []
    for field in ("deliverable", "target_reader", "language", "version_target"):
        if not str(scope.get(field, "")).strip():
            findings.append(_finding("drafting-scope-incomplete", "major", f"scope.{field}", "项目书写作范围缺少必要信息。"))

    template = dict(official_template or {})
    template_digest = str(template.get("sha256", "")).lower()
    if (
        template.get("source") != "NSFC Grants System"
        or template.get("program_type") != program_type
        or str(template.get("guideline_year", "")) != str(guideline_year)
        or not re.fullmatch(r"[0-9a-f]{64}", template_digest)
    ):
        findings.append(_finding(
            "drafting-template-not-bound", "major", "official_template",
            "尚未绑定当前年度和项目类型的官方申请书，不能确定最终章节与篇幅。",
        ))

    canon_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(research_canon, start=1):
        fact_id = str(row.get("id", "")).strip()
        statement = str(row.get("statement", row.get("fact", ""))).strip()
        if not fact_id or not statement or fact_id in canon_by_id:
            findings.append(_finding("research-canon-invalid", "major", f"research_canon.{index}", "研究事实必须具有唯一编号和明确陈述。"))
            continue
        canon_by_id[fact_id] = row

    claims_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(evidence_table, start=1):
        claim_id = str(row.get("claim_id", "")).strip()
        claim = str(row.get("claim", "")).strip()
        status = str(row.get("status", "")).strip()
        source_ids = [str(value) for value in row.get("source_ids", []) if str(value)]
        if not claim_id or not claim or claim_id in claims_by_id:
            findings.append(_finding("evidence-claim-invalid", "major", f"evidence_table.{index}", "证据表中的主张必须具有唯一编号和明确表述。"))
            continue
        claims_by_id[claim_id] = row
        if status not in _PROPOSAL_EVIDENCE_STATUSES:
            findings.append(_finding("proposal-evidence-status-unsupported", "major", claim_id, "主张使用了未登记的申请书证据类型。", status=status))
        missing_sources = sorted(set(source_ids) - set(canon_by_id))
        if missing_sources:
            findings.append(_finding("claim-source-missing", "major", claim_id, "主张引用了研究事实表中不存在的来源。", source_ids=missing_sources))
        if status not in {"biological-inference", "candidate", "hypothesis", "to-be-tested"} and not source_ids:
            findings.append(_finding("evidence-backed-claim-without-source", "major", claim_id, "该类事实性主张没有绑定来源。"))

    evidence_foundation_summary = _review_proposal_evidence_foundation(
        dict(evidence_foundation or {}), claims_by_id, findings,
    )

    required_argument_fields = ("scientific_tension", "central_question", "central_hypothesis", "knowledge_advance")
    for field in required_argument_fields:
        if not str(argument_map.get(field, "")).strip():
            findings.append(_finding("argument-map-incomplete", "major", f"argument_map.{field}", "中心论证缺少必要组成。"))
    if not argument_map.get("alternative_explanations"):
        findings.append(_finding("alternative-explanations-missing", "major", "argument_map.alternative_explanations", "中心假说没有设置需要排除的替代解释。"))

    program_profile = profile["programs"][program_type]
    required_roles = set(program_profile.get("publicly_confirmed_body_sections", []))
    if not required_roles:
        required_roles = {str(value) for value in template.get("required_semantic_roles", []) if str(value)}
    section_blueprints: list[dict[str, Any]] = []
    declared_roles: set[str] = set()
    section_claim_sets: dict[str, set[str]] = {}
    for index, contract in enumerate(section_contracts, start=1):
        section_id = str(contract.get("id", f"section-{index}"))
        role = str(contract.get("role", "")).strip()
        purpose = str(contract.get("purpose", "")).strip()
        question = str(contract.get("scientific_question", "")).strip()
        claim_ids = {str(value) for value in contract.get("claim_ids", []) if str(value)}
        evidence_ids = {str(value) for value in contract.get("evidence_ids", []) if str(value)}
        if not role or not purpose or not question:
            findings.append(_finding("section-contract-incomplete", "major", section_id, "章节必须说明功能、科学问题和写作目的。"))
        declared_roles.add(role)
        section_claim_sets[role] = claim_ids
        unknown_claims = sorted(claim_ids - set(claims_by_id))
        unknown_evidence = sorted(evidence_ids - set(canon_by_id))
        if unknown_claims or unknown_evidence:
            findings.append(_finding("section-evidence-binding-invalid", "major", section_id, "章节引用了未登记的主张或证据。", claim_ids=unknown_claims, evidence_ids=unknown_evidence))
        if not claim_ids:
            findings.append(_finding("section-without-writeable-claims", "major", section_id, "该章节没有可写入正文的已登记主张。"))
        section_blueprints.append({
            "id": section_id,
            "role": role,
            "purpose": purpose,
            "reader_question": question,
            "argument_moves": list(contract.get("paragraph_moves") or _SECTION_WRITING_MOVES.get(role, ["提出问题", "提供证据", "形成结论"])),
            "writeable_claims": [claims_by_id[claim_id]["claim"] for claim_id in sorted(claim_ids & set(claims_by_id))],
            "source_ids": sorted(evidence_ids),
            "allowed_claim_ids": sorted(claim_ids),
            "forbidden_claims": list(contract.get("forbidden_claims", [])),
            "closing_function": str(contract.get("closing_function", "推进下一项科学问题")),
        })
    missing_roles = sorted(required_roles - declared_roles)
    if missing_roles:
        findings.append(_finding("required-drafting-section-missing", "major", "section_contracts", "缺少当前模板要求的正文角色。", missing_roles=missing_roles))
    content_claims = section_claim_sets.get("research_content", set())
    plan_claims = section_claim_sets.get("research_plan", set()) | section_claim_sets.get("technical_route", set())
    if content_claims and plan_claims and len(content_claims & plan_claims) / max(1, len(content_claims | plan_claims)) >= 0.8:
        findings.append(_finding("content-plan-duplication", "major", "section_contracts", "研究内容与研究方案使用了几乎相同的主张集合，应分别回答“研究什么”和“怎样判定”。"))

    aim_ids: set[str] = set()
    aim_matrix: list[dict[str, Any]] = []
    core_phenotypes = {str(value).lower() for value in argument_map.get("core_phenotypes", []) if str(value)}
    central_mechanisms = {str(value).lower() for value in argument_map.get("central_mechanisms", []) if str(value)}
    global_model_aims: set[str] = set()
    for index, aim in enumerate(aims, start=1):
        aim_id = str(aim.get("id", f"aim-{index}"))
        aim_ids.add(aim_id)
        if str(aim.get("model_type", "")) == "global-knockout":
            global_model_aims.add(aim_id)
        missing = [field for field in ("objective", "hypothesis", "approach", "readouts", "alternative_models", "feasibility_evidence", "fallback") if not aim.get(field)]
        if missing:
            findings.append(_finding("drafting-aim-incomplete", "major", aim_id, "研究目标缺少形成完整科学论证所需的信息。", missing=missing))
        phenotypes = {str(value).lower() for value in aim.get("phenotypes", []) if str(value)}
        mechanisms = {str(value).lower() for value in aim.get("mechanisms", []) if str(value)}
        if core_phenotypes or central_mechanisms:
            if not (phenotypes & core_phenotypes or mechanisms & central_mechanisms):
                findings.append(_finding("drafting-aim-outside-central-question", "major", aim_id, "研究目标未对应核心表型或中心机制。"))
        if aim.get("scope_role") == "broad-survey" and not aim.get("decision_value"):
            findings.append(_finding("aim-scope-expansion", "major", aim_id, "大范围普查未说明将改变哪项科学决策。"))
        aim_matrix.append({
            "id": aim_id,
            "objective": aim.get("objective"),
            "hypothesis": aim.get("hypothesis"),
            "phenotypes": sorted(phenotypes),
            "mechanisms": sorted(mechanisms),
            "approach": aim.get("approach"),
            "readouts": list(aim.get("readouts", [])),
            "alternative_models": list(aim.get("alternative_models", [])),
            "decision_value": aim.get("decision_value"),
            "fallback": aim.get("fallback"),
            "depends_on_aim_ids": list(aim.get("depends_on_aim_ids", [])),
        })
    for aim in aims:
        if str(aim.get("model_type", "")) == "conditional-knockout" and aim.get("requires_prior_global_phenotype") is True:
            dependencies = {str(value) for value in aim.get("depends_on_aim_ids", [])}
            if not dependencies & global_model_aims:
                findings.append(_finding("conditional-model-order-unresolved", "major", str(aim.get("id", "conditional-aim")), "条件性模型未依赖先行的整体表型确认目标。"))

    annual_rows = list(annual_plan or [])
    mapped_aims: set[str] = set()
    for index, row in enumerate(annual_rows, start=1):
        row_aims = {str(value) for value in row.get("aim_ids", []) if str(value)}
        mapped_aims.update(row_aims)
        if not row.get("year") or not row_aims or not row.get("milestones") or not row.get("decision_output"):
            findings.append(_finding("annual-plan-row-incomplete", "major", f"annual_plan.{index}", "年度计划必须对应目标、里程碑和年度科学决策。"))
        unknown_aims = sorted(row_aims - aim_ids)
        if unknown_aims:
            findings.append(_finding("annual-plan-unknown-aim", "major", f"annual_plan.{index}", "年度计划引用了不存在的研究目标。", aim_ids=unknown_aims))
    if annual_rows and mapped_aims != aim_ids:
        findings.append(_finding("annual-plan-aim-coverage-incomplete", "major", "annual_plan", "年度计划没有覆盖全部研究目标。", missing_aim_ids=sorted(aim_ids - mapped_aims)))

    existing = list(existing_sections or [])
    if mode in {"revise", "hybrid"} and not existing:
        findings.append(_finding("revision-source-text-missing", "major", "existing_sections", "修订模式缺少需要修改的原文。"))
    revision_briefs = []
    for row in existing:
        text = str(row.get("text", ""))
        role = str(row.get("role", "unclassified"))
        language_result = audit_biomedical_terminology(text, list(row.get("terminology", [])), role) if text.strip() else {"findings": []}
        revision_briefs.append({
            "id": row.get("id"),
            "role": role,
            "preserve": list(row.get("protected_claim_ids", [])),
            "problems": [item["message"] for item in language_result["findings"]],
            "required_moves": _SECTION_WRITING_MOVES.get(role, []),
        })

    major_count = sum(item["severity"] == "major" for item in findings)
    drafting_order = [
        "冻结研究事实和证据边界",
        "完成中心科学问题、假说和替代解释",
        "先写研究内容、判别性读出和研究基础",
        "再写立项依据与科学意义",
        "最后完成中英文摘要、题目、年度计划和创新性",
        "进行术语、机制主张、引文和 Word 逐页复核",
    ]
    return {
        "profile": {
            "version": NSFC_PROFILE_VERSION,
            "guideline_year": guideline_year,
            "program_type": program_type,
            "name_zh": program_profile["name_zh"],
            "positioning": program_profile["positioning"],
            "writing_emphasis": list(program_profile["writing_emphasis"]),
        },
        "mode": mode,
        "central_narrative": {
            "scientific_tension": argument_map.get("scientific_tension"),
            "central_question": argument_map.get("central_question"),
            "central_hypothesis": argument_map.get("central_hypothesis"),
            "knowledge_advance": argument_map.get("knowledge_advance"),
            "alternative_explanations": list(argument_map.get("alternative_explanations", [])),
        },
        "section_blueprints": section_blueprints,
        "aim_matrix": aim_matrix,
        "annual_plan": annual_rows,
        "revision_briefs": revision_briefs,
        "evidence_foundation_summary": evidence_foundation_summary,
        "drafting_order": drafting_order,
        "review_dimensions": [
            "科学问题是否明确且可检验", "现有认识与关键缺口之间是否形成科学张力", "每项主张是否匹配证据强度",
            "立项依据、目标、方法和预期判断是否闭合", "关键实验与模型是否可行", "创新性是否体现知识增量",
            "风险和替代解释是否可处理", "中文表达是否自然、准确并符合生命科学标书语体",
        ],
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_section_drafting": major_count == 0,
        "agent_delivery_contract": {
            "when_ready": "根据章节蓝图撰写或修订实际申请书正文，并完成逐段科学复核。",
            "final_response_must_include": ["drafted_or_revised_prose", "evidence_boundaries", "unresolved_author_inputs"],
            "audit_only_delivery_forbidden": True,
            "internal_package_should_not_replace_prose": True,
            "post_draft_review_modules": list(_PROPOSAL_POST_DRAFT_REVIEW_MODULES),
            "proposal_figure_module": "nsfc-proposal-figure-development",
            "programme_figure_emphasis": _PROPOSAL_PROGRAM_FIGURE_EMPHASIS[program_type],
            "proposal_figure_roles": list(_PROPOSAL_FIGURE_ROLES),
        },
        "input_digest": _digest({
            "guideline_year": guideline_year, "program_type": program_type, "mode": mode, "scope": scope,
            "research_canon": research_canon, "evidence_table": evidence_table, "argument_map": argument_map,
            "section_contracts": section_contracts, "aims": aims, "official_template": template,
            "annual_plan": annual_rows, "existing_sections": existing, "evidence_foundation": evidence_foundation,
        }),
    }


def prepare_nsfc_proposal_figure(
    figure_id: str,
    figure_role: str,
    program_type: str,
    core_message: str,
    section_context: dict[str, Any],
    evidence_records: list[dict[str, Any]],
    visual_plan: dict[str, Any],
    source_attributions: list[dict[str, Any]],
    output_contract: dict[str, Any],
    qa_rounds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prepare a proposal-positioned image prompt and editable reconstruction brief.

    Image generation supplies a scientifically constrained visual reference or
    isolated biological assets. Text, connectors, quantitative panels and the
    final composition remain editable and evidence-bound. A first render is
    never accepted without a recorded, final-size visual review.
    """
    profile = _load_nsfc_profile()
    if program_type not in profile["programs"]:
        raise ValueError("program_type is unsupported")
    if figure_role not in _PROPOSAL_FIGURE_ROLES:
        raise ValueError("figure_role is unsupported")
    role = _PROPOSAL_FIGURE_ROLES[figure_role]
    findings: list[dict[str, Any]] = []
    if not str(figure_id).strip() or not str(core_message).strip():
        findings.append(_finding("proposal-figure-identity-incomplete", "major", "figure", "图号和单一核心信息必须明确。"))

    required_context = ("preceding_claim_ids", "following_question", "allowed_conclusion", "forbidden_implications")
    missing_context = [field for field in required_context if not section_context.get(field)]
    if missing_context:
        findings.append(_finding(
            "proposal-figure-context-incomplete", "major", "section_context",
            "项目书插图必须说明前文依据、后续问题、允许结论和禁止暗示。", missing=missing_context,
        ))

    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_roles: set[str] = set()
    for index, row in enumerate(evidence_records, start=1):
        evidence_id = str(row.get("id", "")).strip()
        required = ("id", "claim", "evidence_status", "source_kind", "source_id", "review_status")
        missing = [field for field in required if not row.get(field)]
        if missing or not evidence_id or evidence_id in evidence_by_id:
            findings.append(_finding(
                "proposal-figure-evidence-invalid", "major", f"evidence_records.{index}",
                "图中证据必须具有唯一编号、主张、证据状态、来源、来源类型和内容审阅状态。", missing=missing,
            ))
            continue
        evidence_by_id[evidence_id] = row
        evidence_roles.add(str(row.get("evidence_role", "")))
        if row.get("source_kind") == "literature" and (
            row.get("citation_identity_status") != "verified_match"
            or row.get("review_status") not in {"full-text-reviewed", "original-source-reviewed"}
        ):
            findings.append(_finding(
                "proposal-figure-literature-unverified", "major", f"evidence_records.{index}",
                "进入立项依据图或机制示意图的文献证据必须完成引用身份核验和原文审阅。",
            ))
        if row.get("source_kind") == "preliminary" and not re.fullmatch(r"[0-9a-f]{64}", str(row.get("artifact_sha256", "")).lower()):
            findings.append(_finding(
                "proposal-figure-preliminary-artifact-unbound", "major", f"evidence_records.{index}",
                "申请人前期结果必须绑定真实研究文件及其校验值。",
            ))
    missing_evidence_roles = sorted(role["required_evidence_roles"] - evidence_roles)
    if missing_evidence_roles:
        findings.append(_finding(
            "proposal-figure-evidence-role-missing", "major", "evidence_records",
            "该位置的插图缺少必要的证据角色。", missing_roles=missing_evidence_roles,
        ))

    nodes = list(visual_plan.get("nodes") or [])
    edges = list(visual_plan.get("edges") or [])
    panels = list(visual_plan.get("panels") or [])
    biological_assets = list(visual_plan.get("biological_assets") or [])
    visual_balance = dict(visual_plan.get("visual_balance") or {})
    minimum_assets = 3 if figure_role in {
        "rationale-evidence-synthesis", "scientific-hypothesis", "achievement-lineage",
    } else 2
    if len(biological_assets) < minimum_assets:
        findings.append(_finding(
            "proposal-figure-visual-elements-insufficient", "major", "visual_plan.biological_assets",
            "项目书插图必须由与科学问题直接相关的组织、细胞、亚细胞、分子、实验模型或真实数据元素承担主要叙事，不能只排文字框。",
            minimum_required=minimum_assets,
        ))
    asset_weights: list[float] = []
    asset_information: list[str] = []
    for index, asset in enumerate(biological_assets, start=1):
        if not isinstance(asset, dict) or any(not asset.get(field) for field in (
            "name", "scale", "scientific_role", "visual_form", "distinct_information",
        )):
            findings.append(_finding(
                "proposal-figure-visual-element-incomplete", "major", f"visual_plan.biological_assets.{index}",
                "每个非文字视觉元素必须说明对象、所处尺度、科学作用、具体表现形式及其不可替代的信息贡献。",
            ))
            continue
        weight = asset.get("importance_weight")
        if not isinstance(weight, (int, float)) or not 0 < float(weight) <= 1:
            findings.append(_finding(
                "proposal-figure-element-weight-invalid", "major", f"visual_plan.biological_assets.{index}.importance_weight",
                "每个视觉元素必须给出与科学叙事相符的相对权重，以便反向检查主次关系。",
            ))
        else:
            asset_weights.append(float(weight))
        asset_information.append(str(asset.get("distinct_information", "")).strip().casefold())
        if not asset.get("label") and not asset.get("label_exemption_reason"):
            findings.append(_finding(
                "proposal-figure-element-label-missing", "major", f"visual_plan.biological_assets.{index}",
                "科学元素原则上必须具有简洁文字标识；特殊场景省略标识时必须说明理由。",
            ))
    if asset_weights and abs(sum(asset_weights) - 1.0) > 0.02:
        findings.append(_finding(
            "proposal-figure-element-weights-unbalanced", "major", "visual_plan.biological_assets",
            "视觉元素权重应归一化，以便检查主视觉、辅助视觉与背景元素是否符合科学逻辑。",
            observed_total=round(sum(asset_weights), 4),
        ))
    nonempty_information = [value for value in asset_information if value]
    if len(set(nonempty_information)) != len(nonempty_information):
        findings.append(_finding(
            "proposal-figure-redundant-elements", "major", "visual_plan.biological_assets",
            "不同视觉元素必须承担不同的信息任务，不能用重复装饰制造虚假丰富度。",
        ))
    non_text_fraction = visual_balance.get("non_text_visual_fraction")
    scale_layers = list(visual_balance.get("scale_layers") or [])
    if not isinstance(non_text_fraction, (int, float)) or not 0.55 <= float(non_text_fraction) <= 0.85:
        findings.append(_finding(
            "proposal-figure-text-dominant", "major", "visual_plan.visual_balance.non_text_visual_fraction",
            "非文字科学视觉元素应占主要面积，同时保留足够空间供短标签、图例和引用清晰排版。",
        ))
    if len(scale_layers) < 2:
        findings.append(_finding(
            "proposal-figure-scale-context-thin", "major", "visual_plan.visual_balance.scale_layers",
            "插图至少应明确两个与问题相关的生物学或实验尺度，避免退化为抽象流程框。",
        ))
    typography = dict(visual_balance.get("typography") or {})
    font_families = [str(value) for value in typography.get("font_families", []) if str(value).strip()]
    font_sizes = dict(typography.get("font_size_levels_pt") or {})
    font_colors = [str(value) for value in typography.get("font_colors", []) if str(value).strip()]
    if not 1 <= len(font_families) <= 2 or not 2 <= len(font_sizes) <= 4 or not 1 <= len(font_colors) <= 3:
        findings.append(_finding(
            "proposal-figure-typography-inconsistent", "major", "visual_plan.visual_balance.typography",
            "字体家族、字号层级和文字颜色必须保持克制且一致：最多两种字体、二至四级字号、最多三种文字颜色。",
        ))
    elif any(not isinstance(value, (int, float)) or float(value) < float(output_contract.get("minimum_text_pt", 0) or 0) for value in font_sizes.values()):
        findings.append(_finding(
            "proposal-figure-font-size-too-small", "major", "visual_plan.visual_balance.typography.font_size_levels_pt",
            "所有字号层级在最终插入尺寸下都不得小于输出合同规定的最小字号。",
        ))
    layer_order = [str(value) for value in visual_balance.get("layer_order", [])]
    required_layers = {"background", "biological-assets", "connectors", "labels", "legend"}
    if not required_layers.issubset(layer_order) or layer_order.index("labels") < layer_order.index("biological-assets") or layer_order.index("labels") < layer_order.index("connectors"):
        findings.append(_finding(
            "proposal-figure-layer-order-unsafe", "major", "visual_plan.visual_balance.layer_order",
            "图层顺序必须显式登记，文字和图例应位于生物学元素及连接线之上，避免底层元素遮挡标识。",
        ))
    correspondence_groups = list(visual_balance.get("correspondence_groups") or [])
    if len(nodes) > 1 and not correspondence_groups:
        findings.append(_finding(
            "proposal-figure-correspondence-unmapped", "major", "visual_plan.visual_balance.correspondence_groups",
            "具有逻辑对应关系的节点必须登记为对位组，并在水平或垂直方向保持同级位置。",
        ))
    region_densities = list(visual_balance.get("region_densities") or [])
    density_values = [row.get("information_density") for row in region_densities if isinstance(row, dict)]
    whitespace_fraction = visual_balance.get("whitespace_fraction")
    if (
        len(region_densities) < 3
        or any(not isinstance(value, (int, float)) or not 0 <= float(value) <= 1 for value in density_values)
        or len(density_values) != len(region_densities)
        or (density_values and max(map(float, density_values)) - min(map(float, density_values)) > 0.25)
        or not isinstance(whitespace_fraction, (int, float))
        or not 0.15 <= float(whitespace_fraction) <= 0.40
    ):
        findings.append(_finding(
            "proposal-figure-spatial-balance-invalid", "major", "visual_plan.visual_balance",
            "至少按三个画面区域评估信息密度，并控制整体留白，避免一侧拥挤而另一侧空洞。",
        ))
    node_by_id: dict[str, dict[str, Any]] = {}
    node_kinds: set[str] = set()
    exact_labels: list[str] = []
    for index, node in enumerate(nodes, start=1):
        node_id = str(node.get("id", "")).strip()
        kind = str(node.get("kind", "")).strip()
        label = str(node.get("label", "")).strip()
        evidence_ids = {str(value) for value in node.get("evidence_ids", []) if str(value)}
        if not node_id or not label or node_id in node_by_id or kind not in _PROPOSAL_FIGURE_NODE_KINDS:
            findings.append(_finding(
                "proposal-figure-node-invalid", "major", f"visual_plan.nodes.{index}",
                "图中节点必须具有唯一编号、准确标签和受支持的科学角色。",
            ))
            continue
        if kind in {"established", "preliminary", "achievement", "knowledge-advance"} and not evidence_ids:
            findings.append(_finding(
                "proposal-figure-node-without-evidence", "major", f"visual_plan.nodes.{index}",
                "事实、前期结果或学术贡献节点必须连接已登记证据。",
            ))
        unknown = sorted(evidence_ids - set(evidence_by_id))
        if unknown:
            findings.append(_finding(
                "proposal-figure-node-evidence-missing", "major", f"visual_plan.nodes.{index}",
                "图中节点引用了未登记证据。", evidence_ids=unknown,
            ))
        node_by_id[node_id] = node
        node_kinds.add(kind)
        exact_labels.append(label)
    missing_node_kinds = sorted(role["required_node_kinds"] - node_kinds)
    if missing_node_kinds:
        findings.append(_finding(
            "proposal-figure-node-role-missing", "major", "visual_plan.nodes",
            "该位置的插图缺少必要的科学叙事节点。", missing_kinds=missing_node_kinds,
        ))

    allowed_relations = {"supports", "weakens", "refutes", "tests", "depends-on", "branches", "alternative", "causal"}
    for index, edge in enumerate(edges, start=1):
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        relation = str(edge.get("relation", ""))
        evidence_ids = {str(value) for value in edge.get("evidence_ids", []) if str(value)}
        if source not in node_by_id or target not in node_by_id or relation not in allowed_relations:
            findings.append(_finding(
                "proposal-figure-edge-invalid", "major", f"visual_plan.edges.{index}",
                "连接线必须连接已登记节点，并明确表示支持、反驳、检验、依赖、分支、替代或因果关系。",
            ))
            continue
        if relation in {"supports", "weakens", "refutes", "causal"} and not evidence_ids:
            findings.append(_finding(
                "proposal-figure-edge-evidence-missing", "major", f"visual_plan.edges.{index}",
                "表达事实关系或因果关系的连接线必须绑定证据。",
            ))
        if relation == "causal":
            causal_statuses = {str(evidence_by_id[evidence_id].get("evidence_status", "")) for evidence_id in evidence_ids if evidence_id in evidence_by_id}
            if not causal_statuses or causal_statuses - {"mechanism", "causal"}:
                findings.append(_finding(
                    "proposal-figure-causal-arrow-overclaim", "major", f"visual_plan.edges.{index}",
                    "确定性因果箭头只能用于已经达到机制或因果层级的证据；待检验关系应使用虚线并标注为假说。",
                ))

    for index, panel in enumerate(panels, start=1):
        panel_kind = str(panel.get("kind", ""))
        if panel_kind in {"quantitative-plot", "microscopy", "blot", "sequencing", "structure-prediction"}:
            if not re.fullmatch(r"[0-9a-f]{64}", str(panel.get("source_artifact_sha256", "")).lower()):
                findings.append(_finding(
                    "proposal-figure-observed-panel-unbound", "major", f"visual_plan.panels.{index}",
                    "真实数据 panel 必须绑定来源文件，不能由图像生成模型合成。",
                ))
            if panel.get("renderer") not in {"publication-figure-package", "analysis-specific-renderer", "observed-image-layout"}:
                findings.append(_finding(
                    "proposal-figure-observed-panel-renderer-invalid", "major", f"visual_plan.panels.{index}",
                    "真实数据 panel 必须使用确定性绘图器或原始图像排版，不能交给图像生成模型。",
                ))

    attribution_by_source = {str(row.get("source_id", "")): row for row in source_attributions if row.get("source_id")}
    referenced_source_ids = {str(row.get("source_id", "")) for row in evidence_records if row.get("source_id")}
    missing_attribution = sorted(referenced_source_ids - set(attribution_by_source))
    if missing_attribution:
        findings.append(_finding(
            "proposal-figure-attribution-missing", "major", "source_attributions",
            "插图所依据的文献、数据库或前期结果必须在图题和来源表中明确归属。", source_ids=missing_attribution,
        ))
    for index, row in enumerate(source_attributions, start=1):
        if row.get("usage") in {"adapted-visual", "reproduced-visual"} and row.get("permission_status") not in {"licensed", "permission-obtained", "public-domain"}:
            findings.append(_finding(
                "proposal-figure-visual-permission-unresolved", "major", f"source_attributions.{index}",
                "改编或复用他人图像必须记录许可状态；概念重绘也要在图题中注明依据。",
            ))

    required_output = (
        "final_width_mm", "text_area_width_mm", "max_height_mm", "minimum_text_pt", "formats", "language",
        "figure_paragraph_alignment", "figure_paragraph_prefix",
    )
    missing_output = [field for field in required_output if field not in output_contract or (field != "figure_paragraph_prefix" and not output_contract.get(field))]
    formats = {str(value).lower() for value in output_contract.get("formats", [])}
    if missing_output or not {"pptx", "pdf", "png"}.issubset(formats):
        findings.append(_finding(
            "proposal-figure-output-contract-incomplete", "major", "output_contract",
            "项目书插图必须固定最终尺寸、最小字号、语言，并交付可编辑 PPTX、PDF 和 PNG。", missing=missing_output,
        ))
    final_width = output_contract.get("final_width_mm")
    text_area_width = output_contract.get("text_area_width_mm")
    if (
        not isinstance(final_width, (int, float))
        or not isinstance(text_area_width, (int, float))
        or float(final_width) > float(text_area_width)
    ):
        findings.append(_finding(
            "proposal-figure-exceeds-text-area", "major", "output_contract.final_width_mm",
            "图件宽度不得超过申请书正文版心宽度。",
        ))
    if output_contract.get("figure_paragraph_alignment") != "center" or output_contract.get("figure_paragraph_prefix") != "":
        findings.append(_finding(
            "proposal-figure-paragraph-placement-invalid", "major", "output_contract",
            "图件所在段落必须显式居中，且图件前不得保留空格、制表符或其他占位字符。",
        ))

    major_count = sum(item["severity"] == "major" for item in findings)
    program = profile["programs"][program_type]
    programme_figure = _PROPOSAL_PROGRAM_FIGURE_EMPHASIS[program_type]
    base_prompt = "\n".join([
        "Use case: infographic-diagram",
        "Asset type: high-stakes biomedical grant proposal scientific illustration reference",
        f"Proposal programme: {program['name_zh']}",
        f"Programme-specific story: {programme_figure['story']}",
        f"Programme-specific visual priority: {programme_figure['visual_priority']}",
        f"Figure role: {figure_role} — {role['purpose']}",
        f"Primary scientific message: {core_message}",
        f"Scientific composition: {role['composition']}",
        "Visual language: restrained editorial biomedical illustration; accurate anatomy and molecular scale; layered tissue, cellular, subcellular and molecular context only where scientifically relevant; selective depth, cutaway, localization, interaction geometry, model organism silhouette, experimental setup or source-data thumbnail as scientifically appropriate; coherent reading path; clear focal hierarchy; balanced negative space and regional information density; publication-grade balance.",
        "Information density: visually rich but disciplined. Combine scientifically meaningful biological scenes, molecular interactions, experimental model cues and evidence-status zones; do not reduce the composition to generic boxes connected by arrows.",
        f"Biological visual elements that must carry the story: {json.dumps(biological_assets, ensure_ascii=False)}",
        f"Visual balance: {json.dumps(visual_balance, ensure_ascii=False)}. Scientific illustrations, observed-data panels and spatial biological context must occupy the declared majority of the figure; labels remain concise supporting elements.",
        f"Panel structure: {json.dumps(panels, ensure_ascii=False)}",
        "Editable-final strategy: generate the non-text visual reference and separable biological assets only. Keep all labels, citations, arrows, legends, quantitative plots and exact scientific statements out of the bitmap; they will be rebuilt as native editable objects.",
        "Style: flat-to-subtle-volume scientific illustration, clean off-white background, restrained blue-grey base with one muted accent per evidence class, consistent line weight, no glossy plastic, no decorative gradients, no stock-icon collage, no fake microscopy, no pseudo-data, no watermark.",
        f"Scientific prohibitions: {role['forbidden']}",
        f"Programme-specific avoid: {programme_figure['avoid']}",
        f"Forbidden implications: {json.dumps(section_context.get('forbidden_implications', []), ensure_ascii=False)}",
        "Avoid: generic flowchart; equal-weight boxes; dense tiny text; dramatic lighting; oversaturated colors; speculative anatomy; unsupported causal arrows; decorative DNA helices; random laboratory icons; publication logos; journal covers.",
        "Quality: high",
    ])
    reconstruction_prompt = "\n".join([
        "Reconstruct the generated scientific reference as an object-level editable PowerPoint figure, not as a full-slide screenshot.",
        f"Final figure size: {output_contract.get('final_width_mm')} mm wide within a {output_contract.get('text_area_width_mm')} mm text area, no more than {output_contract.get('max_height_mm')} mm high; minimum text {output_contract.get('minimum_text_pt')} pt at final size.",
        "Preserve the biological composition while separating biological visual assets from native editable text, connectors, legend keys, panel labels, borders and group containers.",
        f"Exact editable labels: {json.dumps(exact_labels, ensure_ascii=False)}",
        f"Evidence-style legend: {json.dumps(_PROPOSAL_FIGURE_EVIDENCE_STYLES, ensure_ascii=False)}",
        f"Exact edge semantics: {json.dumps(edges, ensure_ascii=False)}",
        "Use native text boxes for all wording, native connectors for all relations and deterministic source panels for all observed data. Keep substantive biological illustrations as separated visual objects with provenance. Do not replace them with text cards, leave generated pseudo-text, duplicate labels or semantic arrows inside bitmap assets.",
        "Keep same-level labels at one font size, use no more than the declared font families and restrained text colours, and keep corresponding labels or elements on matched horizontal or vertical positions. Enforce the declared z-order so background art, biological assets and connectors cannot cover labels, legends or data. Calibrate wrapping at final page size; keep text inside its containers and away from illustrations; require concise labels for scientific elements unless a documented exception applies. Audit each element's narrative weight and unique information contribution, remove redundant decoration, and rebalance regional density and whitespace. Use an origin-versus-preview comparison; fix clipping, occlusion, crowding, wrong visual hierarchy, misleading arrow direction, colour-status ambiguity and any mismatch between caption and figure before acceptance.",
        "Place the exported figure in its own explicitly centre-aligned paragraph with no leading spaces, tabs, empty runs or placeholder characters; do not exceed the document text boundary. Export object-editable PPTX and derive PDF plus high-resolution PNG from the accepted composition.",
    ])

    rounds = list(qa_rounds or [])
    latest_round = rounds[-1] if rounds else {}
    qa_required_fields = (
        "rendered_artifact_sha256", "reviewed_at_final_size", "scientific_content_checked",
        "citation_attribution_checked", "text_legibility_checked", "layout_hierarchy_checked",
        "caption_alignment_checked", "font_consistency_checked", "color_consistency_checked",
        "z_order_checked", "correspondence_alignment_checked", "text_boundary_checked",
        "label_completeness_checked", "element_weight_redundancy_checked", "spatial_balance_checked",
        "text_width_boundary_checked", "figure_paragraph_centered_checked", "figure_paragraph_placeholder_free_checked",
        "semantic_errors", "layout_errors", "corrections",
    )
    qa_complete = bool(rounds) and all(field in latest_round for field in qa_required_fields)
    qa_passed = bool(
        qa_complete
        and re.fullmatch(r"[0-9a-f]{64}", str(latest_round.get("rendered_artifact_sha256", "")).lower())
        and all(latest_round.get(field) is True for field in (
            "reviewed_at_final_size", "scientific_content_checked", "citation_attribution_checked",
            "text_legibility_checked", "layout_hierarchy_checked", "caption_alignment_checked",
            "font_consistency_checked", "color_consistency_checked", "z_order_checked",
            "correspondence_alignment_checked", "text_boundary_checked", "label_completeness_checked",
            "element_weight_redundancy_checked", "spatial_balance_checked",
            "text_width_boundary_checked", "figure_paragraph_centered_checked", "figure_paragraph_placeholder_free_checked",
        ))
        and latest_round.get("semantic_errors") == []
        and latest_round.get("layout_errors") == []
    )
    return {
        "figure_id": figure_id,
        "figure_role": figure_role,
        "program_type": program_type,
        "section_role": role["section"],
        "programme_figure_emphasis": programme_figure,
        "core_message": core_message,
        "section_context": section_context,
        "prompt_package": {
            "imagegen_reference_prompt": base_prompt,
            "editable_reconstruction_prompt": reconstruction_prompt,
            "imagegen_use_case": "infographic-diagram",
            "imagegen_is_observed_evidence": False,
            "required_reconstruction_runtime": "image-to-editable-ppt",
        },
        "renderer_plan": {
            "conceptual_visual_reference": "imagegen",
            "editable_composition": "image-to-editable-ppt",
            "quantitative_panels": "publication-figure-package or analysis-specific renderer",
            "raw_observed_images": "source-preserving layout with provenance",
        },
        "exact_label_inventory": exact_labels,
        "evidence_style_legend": _PROPOSAL_FIGURE_EVIDENCE_STYLES,
        "source_attributions": source_attributions,
        "output_contract": output_contract,
        "qa_contract": {
            "review_every_render_at_final_size": True,
            "single_targeted_correction_per_iteration": True,
            "acceptance_requires_zero_semantic_errors": True,
            "acceptance_requires_zero_layout_errors": True,
            "acceptance_requires_typography_layer_alignment_and_balance_review": True,
            "rounds": rounds,
        },
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_generation": major_count == 0,
        "ready_for_proposal_insertion": major_count == 0 and qa_passed,
        "revision_required": major_count > 0 or not qa_passed,
        "input_digest": _digest({
            "figure_id": figure_id, "figure_role": figure_role, "program_type": program_type,
            "core_message": core_message, "section_context": section_context,
            "evidence_records": evidence_records, "visual_plan": visual_plan,
            "source_attributions": source_attributions, "output_contract": output_contract,
            "qa_rounds": rounds,
        }),
    }


def audit_nsfc_proposal(
    guideline_year: int,
    program_type: str,
    application_code_1: str,
    research_attribute: str,
    title_cn: str,
    abstract_cn: str,
    abstract_en: str,
    sections: list[dict[str, Any]],
    aims: list[dict[str, Any]],
    core_phenotypes: list[str],
    central_mechanisms: list[str],
    bilingual_concepts: list[dict[str, str]] | None = None,
    entity_prerequisites: list[dict[str, Any]] | None = None,
    official_template: dict[str, Any] | None = None,
    human_genetics_context: dict[str, Any] | None = None,
    annual_plan: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit an NSFC biomedical proposal against a versioned semantic contract.

    Public official rules are kept distinct from workbench scientific-writing
    checks. No funding probability or reviewer score is inferred.
    """
    if guideline_year < 2024:
        raise ValueError("guideline_year must be 2024 or later")
    profile = _load_nsfc_profile()
    if program_type not in profile["programs"]:
        raise ValueError("program_type is unsupported")
    if research_attribute not in NSFC_RESEARCH_ATTRIBUTES:
        raise ValueError("research_attribute must use one of the two current NSFC categories")
    if not isinstance(sections, list) or not isinstance(aims, list):
        raise ValueError("sections and aims must be arrays")

    findings: list[dict[str, Any]] = []
    official_findings: list[dict[str, Any]] = []
    if guideline_year != 2026:
        official_findings.append(_finding(
            "profile-year-not-installed", "major", "guideline_year",
            "当前仅内置 2026 年规则快照；其他年度必须先核对当年项目指南和在线表单。",
        ))
    if program_type in NSFC_LIFE_SCIENCE_PROGRAMS_REQUIRING_SECOND_LEVEL_CODE and not re.fullmatch(r"[A-Z]\d{4}", application_code_1.strip().upper()):
        official_findings.append(_finding(
            "life-science-second-level-code-required", "major", "application_code_1",
            "生命科学部该项目类型的申请代码 1 必须填写到二级代码。",
        ))
    official_template = dict(official_template or {})
    template_digest = str(official_template.get("sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", template_digest) or official_template.get("source") != "NSFC Grants System":
        official_findings.append(_finding(
            "current-official-template-not-bound", "major", "official_template",
            "未绑定从科学基金网络信息系统按当前年度和项目类型下载的官方申请书模板及其校验值。",
        ))
    template_program = str(official_template.get("program_type", ""))
    if template_program and template_program != program_type:
        official_findings.append(_finding(
            "official-template-program-mismatch", "major", "official_template.program_type",
            "官方模板的项目类型与当前申请类型不一致。",
        ))
    if guideline_year == 2026 and str(official_template.get("guideline_year", "")) not in {"", "2026"}:
        official_findings.append(_finding(
            "official-template-year-mismatch", "major", "official_template.guideline_year",
            "官方模板年度与当前申请年度不一致。",
        ))

    human_genetics_context = dict(human_genetics_context or {})
    human_genetics_rows = list(human_genetics_context.get("evidence_rows", []))
    if human_genetics_context.get("human_relevance_claimed") is True and not human_genetics_rows:
        findings.append(_finding(
            "human-genetics-evidence-missing", "major", "human_genetics_context",
            "申请书提出人类疾病或临床相关性，但没有绑定疾病、表型、遗传方式、变异类型、来源和功能桥接证据。",
        ))
    for index, row in enumerate(human_genetics_rows, start=1):
        missing = [field for field in (
            "disease", "phenotype_terms", "inheritance", "variant_class", "source_ids", "evidence_level",
            "proposal_use", "functional_bridge", "mechanism_boundary",
        ) if not row.get(field)]
        if missing:
            findings.append(_finding(
                "human-genetics-row-incomplete", "major", f"human_genetics_context.evidence_rows.{index}",
                "人类遗传学证据行缺少必要字段。", missing=missing,
            ))
        if row.get("proposal_use") == "direct-mechanism-proof":
            findings.append(_finding(
                "clinical-evidence-mechanism-overreach", "major", f"human_genetics_context.evidence_rows.{index}",
                "人类遗传学或临床表型证据可以增强科学意义，但不能单独证明本项目所提出的分子机制。",
            ))
    if _NUMERIC_CITATION.search(abstract_cn) or _NUMERIC_CITATION.search(abstract_en):
        findings.append(_finding(
            "abstract-numeric-citation", "major", "abstract",
            "摘要中检测到编号式文献引用；应在当年在线表单允许范围内改写为不依赖参考文献即可理解的陈述。",
        ))
    if not title_cn.strip() or len(re.findall(r"[\u4e00-\u9fff]", title_cn)) < 6:
        findings.append(_finding("title-insufficient", "major", "title_cn", "中文题目为空或未形成可识别的科学命题。"))
    if re.fullmatch(r"(?:研究背景与问题提出|科学问题与科学假说|研究内容与技术路线|项目研究方案)", title_cn.strip()):
        findings.append(_finding("generic-form-title", "major", "title_cn", "题目只是章节标签，没有表达具体研究对象、关键关系或科学问题。"))
    field_limits = dict(official_template.get("field_limits", {}))
    for field_name, value in (("title_cn", title_cn), ("abstract_cn", abstract_cn), ("abstract_en", abstract_en)):
        maximum = field_limits.get(f"{field_name}_max_characters")
        if isinstance(maximum, int) and maximum > 0 and len(value) > maximum:
            findings.append(_finding("official-field-length-exceeded", "major", field_name, "文本超过当前官方模板登记的字符上限。", observed=len(value), maximum=maximum))

    concept_findings: list[dict[str, Any]] = []
    for index, concept in enumerate(bilingual_concepts or [], start=1):
        cn = str(concept.get("cn", "")).strip()
        en = str(concept.get("en", "")).strip()
        concept_id = str(concept.get("id", f"concept-{index}"))
        if not cn or not en:
            concept_findings.append(_finding("bilingual-concept-incomplete", "major", concept_id, "中英文核心概念映射不完整。"))
            continue
        if cn not in abstract_cn:
            concept_findings.append(_finding("concept-missing-from-chinese-abstract", "major", concept_id, f"中文摘要未出现核心概念“{cn}”。"))
        if not re.search(rf"(?<![A-Za-z0-9]){re.escape(en)}(?![A-Za-z0-9])", abstract_en, re.IGNORECASE):
            concept_findings.append(_finding("concept-missing-from-english-abstract", "major", concept_id, f"英文摘要未出现核心概念“{en}”。"))
    findings.extend(concept_findings)

    section_inventory: list[dict[str, Any]] = []
    section_ids: set[str] = set()
    paragraph_registry: list[dict[str, Any]] = []
    for section_index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError("sections must contain objects")
        heading = str(section.get("heading", "")).strip()
        text = str(section.get("text", "")).strip()
        section_id = str(section.get("id", "")).strip() or _normalize_section_name(heading)
        section_role = str(section.get("role", "")).strip() or _normalize_section_name(heading)
        section_ids.add(section_id)
        section_inventory.append({"id": section_id, "role": section_role, "heading": heading, "character_count": len(text)})
        if section_role == "rationale" and _SECTION_OPERATION_TERMS.search(text):
            findings.append(_finding(
                "method-contamination-in-rationale", "major", section_id,
                "立项依据中出现成段的拟执行操作；应保留问题、现状、缺口和科学假设，将具体操作移入研究方案。",
            ))
        if section_role == "preliminary" and text and not _PRELIMINARY_DATA_TERMS.search(text):
            findings.append(_finding(
                "preliminary-section-lacks-project-evidence", "major", section_id,
                "研究基础未识别到申请团队的前期数据或可行性证据，不能仅以文献综述代替。",
            ))
        heading_claim = str(section.get("heading_claim", "")).strip()
        knowledge_change = str(section.get("knowledge_change", "")).strip()
        if heading and section_role not in {"abstract_cn", "abstract_en", "references", "unclassified"}:
            if not heading_claim:
                findings.append(_finding("heading-proposition-missing", "minor", section_id, "该部分未声明标题所承诺的科学命题，无法检查标题与正文是否一致。"))
            elif heading_claim not in text:
                findings.append(_finding("heading-body-incongruence", "major", section_id, "正文未直接回答标题所承诺的科学命题。"))
            if not knowledge_change:
                findings.append(_finding("scientific-meaning-missing", "major", section_id, "未说明该部分结果将改变哪一项现有认识。"))
        paragraphs = section.get("paragraphs", [])
        if paragraphs and not isinstance(paragraphs, list):
            raise ValueError("section paragraphs must be arrays")
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            if not isinstance(paragraph, dict):
                raise ValueError("paragraphs must contain objects")
            paragraph_role = str(paragraph.get("role", ""))
            paragraph_registry.append({
                "id": str(paragraph.get("id", f"{section_id}-p{paragraph_index}")),
                "section_id": section_id,
                "order": len(paragraph_registry),
                "text": str(paragraph.get("text", "")),
                "question_id": str(paragraph.get("question_id", "")),
                "advances_question_ids": list(paragraph.get("advances_question_ids", [])),
                "role": paragraph_role,
            })
            allowed_paragraph_roles = {
                "rationale": {"background", "field_consensus", "research_status", "gap", "scientific_significance", "scientific_question", "hypothesis", "project_entry"},
                "research_status": {"field_consensus", "direct_evidence", "conflicting_evidence", "gap"},
                "preliminary": {"preliminary_result", "feasibility", "technical_readiness", "remaining_gap"},
                "research_content": {"objective", "hypothesis", "approach", "readout", "alternative_interpretation", "decision"},
                "research_plan": {"design", "method", "control", "statistics", "quality_control", "risk", "fallback"},
            }
            if paragraph_role and section_role in allowed_paragraph_roles and paragraph_role not in allowed_paragraph_roles[section_role]:
                findings.append(_finding(
                    "paragraph-section-role-mismatch", "major", paragraph_registry[-1]["id"],
                    "该段承担的任务不属于当前章节，应移动到对应章节或改写其功能。",
                    paragraph_role=paragraph_role, section_role=section_role,
                ))
    for current, previous in zip(paragraph_registry[1:], paragraph_registry):
        if current["section_id"] == previous["section_id"] and previous["question_id"] and current["question_id"]:
            if previous["question_id"] != current["question_id"] and previous["question_id"] not in current["advances_question_ids"]:
                findings.append(_finding(
                    "paragraph-transition-unresolved", "minor", current["id"],
                    "相邻段落更换了科学问题，但未声明承接关系。",
                    previous_paragraph=previous["id"],
                ))

    entity_positions: dict[str, int] = {}
    joined_paragraphs = [item["text"] for item in paragraph_registry]
    for row in entity_prerequisites or []:
        entity = str(row.get("entity", "")).strip()
        if not entity:
            continue
        positions = [idx for idx, text in enumerate(joined_paragraphs) if entity in text]
        entity_positions[entity] = positions[0] if positions else 10**9
    for row in entity_prerequisites or []:
        entity = str(row.get("entity", "")).strip()
        for prerequisite in row.get("requires_prior", []):
            if entity_positions.get(str(prerequisite), 10**9) >= entity_positions.get(entity, 10**9):
                findings.append(_finding(
                    "entity-introduction-order", "major", entity,
                    f"“{entity}”在其必要前置概念“{prerequisite}”之前出现或前置概念缺失。",
                ))

    phenotype_set = {str(value).strip().lower() for value in core_phenotypes if str(value).strip()}
    mechanism_set = {str(value).strip().lower() for value in central_mechanisms if str(value).strip()}
    aim_alignment: list[dict[str, Any]] = []
    aim_ids: set[str] = set()
    global_model_aims: set[str] = set()
    for index, aim in enumerate(aims, start=1):
        if not isinstance(aim, dict):
            raise ValueError("aims must contain objects")
        aim_id = str(aim.get("id", f"aim-{index}"))
        if aim_id in aim_ids:
            raise ValueError("aim ids must be unique")
        aim_ids.add(aim_id)
        if str(aim.get("model_type", "")) == "global-knockout":
            global_model_aims.add(aim_id)
        phenotypes = {str(value).strip().lower() for value in aim.get("phenotypes", []) if str(value).strip()}
        mechanisms = {str(value).strip().lower() for value in aim.get("mechanisms", []) if str(value).strip()}
        aligned_phenotypes = sorted(phenotypes & phenotype_set)
        aligned_mechanisms = sorted(mechanisms & mechanism_set)
        readouts = list(aim.get("readouts", []))
        discriminates = list(aim.get("discriminates_alternatives", []))
        alignment = {
            "aim_id": aim_id,
            "core_phenotypes": aligned_phenotypes,
            "central_mechanisms": aligned_mechanisms,
            "readout_count": len(readouts),
            "alternative_model_count": len(discriminates),
        }
        aim_alignment.append(alignment)
        if not aligned_phenotypes and not aligned_mechanisms:
            findings.append(_finding("aim-outside-central-question", "major", aim_id, "该研究目标既未连接核心表型，也未连接中心机制。"))
        if not readouts:
            findings.append(_finding("aim-readout-missing", "major", aim_id, "未声明能够回答该目标的判别性观测指标。"))
        if not discriminates:
            findings.append(_finding("aim-alternative-model-test-missing", "minor", aim_id, "未说明结果如何区分至少两个可替代解释。"))
        if not aim.get("feasibility_evidence"):
            findings.append(_finding("aim-feasibility-evidence-missing", "major", aim_id, "未绑定前期可行性证据。"))
        if not aim.get("fallback"):
            findings.append(_finding("aim-fallback-missing", "major", aim_id, "未声明失败时仍可回答科学问题的替代方案。"))
        if aim.get("scope_role") == "broad-survey" and not aim.get("decision_value"):
            findings.append(_finding("aim-scope-expansion", "major", aim_id, "大范围普查没有说明将改变哪项科学判断，属于范围膨胀。"))
        model_role = str(aim.get("model_role", "")).strip()
        if model_role == "expression_localization" and re.search(r"(?:Cre|cre|条件敲除|conditional knockout)", str(aim.get("model", ""))):
            findings.append(_finding("model-role-mismatch", "major", aim_id, "条件遗传模型不能替代表达定位证据。"))
    for aim in aims:
        if str(aim.get("model_type", "")) == "conditional-knockout" and aim.get("requires_prior_global_phenotype") is True:
            dependencies = {str(value) for value in aim.get("depends_on_aim_ids", [])}
            if not dependencies & global_model_aims:
                findings.append(_finding("conditional-model-order-unresolved", "major", str(aim.get("id", "conditional-aim")), "条件性敲除目标没有连接先行的整体表型确认。"))

    annual_rows = list(annual_plan or [])
    annual_aims: set[str] = set()
    for index, row in enumerate(annual_rows, start=1):
        row_aims = {str(value) for value in row.get("aim_ids", []) if str(value)}
        annual_aims.update(row_aims)
        if not row.get("year") or not row_aims or not row.get("milestones") or not row.get("decision_output"):
            findings.append(_finding("annual-plan-row-incomplete", "major", f"annual_plan.{index}", "年度计划必须对应研究目标、里程碑和年度科学决策。"))
    if annual_rows and annual_aims != aim_ids:
        findings.append(_finding("annual-plan-aim-coverage-incomplete", "major", "annual_plan", "年度计划没有完整对应研究目标。", missing_aim_ids=sorted(aim_ids - annual_aims)))

    program_profile = profile["programs"][program_type]
    required_roles = set(program_profile.get("publicly_confirmed_body_sections", []))
    if not required_roles:
        required_roles = {str(value) for value in official_template.get("required_semantic_roles", []) if str(value)}
        if not required_roles:
            findings.append(_finding(
                "template-semantic-roles-not-imported", "major", "official_template.required_semantic_roles",
                "该项目类型的公开网页未给出可复用的完整撰写提纲；必须从当年官方模板导入正文角色后再审查。",
            ))
    missing_roles = sorted(required_roles - {item["role"] for item in section_inventory})
    if missing_roles:
        findings.append(_finding("nsfc-section-role-missing", "major", "sections", "申请书缺少必要的科学叙事角色。", missing_roles=missing_roles))

    major_count = sum(item["severity"] == "major" for item in [*official_findings, *findings])
    return {
        "agency": "NSFC",
        "agency_profile": {
            "profile_version": NSFC_PROFILE_VERSION,
            "guideline_year": guideline_year,
            "program_type": program_type,
            "research_attribute": research_attribute,
            "application_code_1": application_code_1,
            "official_sources": list(NSFC_OFFICIAL_SOURCES),
            "abstract_length_policy": "confirm-current-online-form-before-delivery",
            "us_nsf_review_criteria_applied": False,
            "program_profile": program_profile,
            "official_template_sha256": template_digest or None,
            "official_template_required": True,
        },
        "official_rule_findings": official_findings,
        "semantic_findings": findings,
        "section_inventory": section_inventory,
        "aim_alignment": aim_alignment,
        "annual_plan_summary": {"year_count": len(annual_rows), "mapped_aim_ids": sorted(annual_aims)},
        "human_genetics_summary": {
            "human_relevance_claimed": human_genetics_context.get("human_relevance_claimed") is True,
            "evidence_row_count": len(human_genetics_rows),
            "recommended_source_modules": ["variant-evidence", "hpo-term-evidence", "gene-evidence"] if human_genetics_context.get("human_relevance_claimed") is True and not human_genetics_rows else [],
        },
        "major_finding_count": major_count,
        "ready_for_scientific_drafting": major_count == 0,
        "limitations": [
            "本模块检查规则、结构和声明之间的一致性，不预测资助结果，也不替代当年项目指南、在线表单或依托单位要求。",
            "未提供原始前期数据时，只能核对其声明位置和证据绑定，不能确认数据真实性或生物学结论。",
        ],
        "input_digest": _digest({
            "title_cn": title_cn, "abstract_cn": abstract_cn, "abstract_en": abstract_en,
            "sections": sections, "aims": aims, "core_phenotypes": core_phenotypes,
            "central_mechanisms": central_mechanisms,
            "official_template": official_template,
            "human_genetics_context": human_genetics_context,
            "annual_plan": annual_rows,
        }),
    }


def audit_biomedical_terminology(
    text: str,
    terminology: list[dict[str, Any]],
    document_section: str,
    styled_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check biomedical naming, abbreviations, Chinese style, and gene/protein distinctions."""
    if not text.strip():
        raise ValueError("text is required")
    findings: list[dict[str, Any]] = []
    first_positions: dict[str, int] = {}
    for index, row in enumerate(terminology, start=1):
        if not isinstance(row, dict):
            raise ValueError("terminology must contain objects")
        concept_id = str(row.get("concept_id", f"term-{index}"))
        preferred = str(row.get("preferred", "")).strip()
        abbreviation = str(row.get("abbreviation", "")).strip()
        allowed = [str(value) for value in row.get("allowed_forms", []) if str(value)]
        entity_type = str(row.get("entity_type", "")).strip()
        if not preferred:
            findings.append(_finding("preferred-term-missing", "major", concept_id, "术语表未声明规范名称。"))
            continue
        positions = [position for form in [preferred, abbreviation, *allowed] if form for position in [text.find(form)] if position >= 0]
        if positions:
            first_positions[concept_id] = min(positions)
        if abbreviation and abbreviation in text:
            first = text.find(abbreviation)
            prefix = text[max(0, first - 120):first]
            if preferred not in prefix and f"（{abbreviation}）" not in text[: first + len(abbreviation) + 2] and f"({abbreviation})" not in text[: first + len(abbreviation) + 2]:
                findings.append(_finding("abbreviation-first-definition-missing", "major", concept_id, f"缩写“{abbreviation}”首次出现时未与规范全称共同定义。"))
        disallowed = [str(value) for value in row.get("disallowed_forms", []) if str(value)]
        for value in disallowed:
            if value in text:
                findings.append(_finding("disallowed-term-form", "major", concept_id, f"检测到不允许的写法“{value}”。", preferred=preferred))
        if entity_type in {"gene", "protein"} and row.get("paired_concept_id") and not row.get("distinction_statement"):
            findings.append(_finding("gene-protein-distinction-undeclared", "major", concept_id, "基因与蛋白使用同一符号时，必须声明各自写法和语义边界。"))

    for match in re.finditer(r"\s—\s|——", text):
        findings.append(_finding("rhetorical-em-dash", "minor", f"character:{match.start()+1}", "检测到修辞性破折号；生物化学复合名称中的连接号不受此规则影响。"))
    for term, replacement in _UNNATURAL_CHINESE.items():
        if term in text:
            findings.append(_finding("unnatural-governance-phrase", "minor", f"character:{text.find(term)+1}", f"“{term}”不适合作为对外申请书表述。", suggested=replacement))
    for term, replacement in _INTERNAL_GOVERNANCE_TERMS.items():
        if term.lower() in text.lower() and document_section not in {"methods-appendix", "internal-audit"}:
            findings.append(_finding("internal-workflow-language", "minor", f"character:{text.lower().find(term.lower())+1}", f"正文中出现内部工作流用语“{term}”。", suggested=replacement))

    sentences = [value.strip() for value in re.split(r"(?<=[。！？!?])", text) if value.strip()]
    for index, sentence in enumerate(sentences, start=1):
        han_count = len(re.findall(r"[\u4e00-\u9fff]", sentence))
        clause_count = len(re.findall(r"[，；：]|(?:由于|因此|从而|并且|同时|而且|但|然而)", sentence))
        if han_count > 70 and clause_count >= 4:
            findings.append(_finding("chinese-clause-stacked-sentence", "minor", f"sentence:{index}", "中文长句包含过多逻辑层次，应拆分为问题、证据和结论明确的句子。", excerpt=sentence[:160]))

    styled_runs = list(styled_runs or [])
    for run in styled_runs:
        concept_id = str(run.get("concept_id", ""))
        entity_type = str(run.get("entity_type", ""))
        italic = bool(run.get("italic", False))
        organism = str(run.get("organism", "")).lower()
        if entity_type == "gene" and organism in {"mouse", "mus musculus", "human", "homo sapiens"} and not italic:
            findings.append(_finding("gene-symbol-style", "major", concept_id or "styled_run", "哺乳动物基因符号在可控制样式的正文中应使用斜体。"))
        if entity_type == "protein" and italic:
            findings.append(_finding("protein-symbol-style", "major", concept_id or "styled_run", "蛋白符号不应沿用基因符号的斜体样式。"))

    major_count = sum(item["severity"] == "major" for item in findings)
    return {
        "document_section": document_section,
        "term_count": len(terminology),
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_external_prose": major_count == 0,
        "first_occurrence_index": first_positions,
        "input_digest": _digest({"text": text, "terminology": terminology, "styled_runs": styled_runs}),
    }


def audit_mechanism_claim_promotion(
    claims: list[dict[str, Any]],
    promotion_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply evidence-specific promotion rules to claims in every proposal section."""
    if not claims:
        raise ValueError("claims must be nonempty")
    rules = {
        "association": {"association_evidence"},
        "function": {"direct_experiment", "phenotype_link"},
        "substrate": {"physical_interaction", "site_specific_modification", "catalytic_dependency"},
        "mechanism": {"physical_interaction", "site_specific_modification", "catalytic_dependency", "phenotype_link"},
        "causal": {"physical_interaction", "site_specific_modification", "catalytic_dependency", "phenotype_link", "rescue"},
    }
    for row in promotion_rules or []:
        level = str(row.get("level", ""))
        if level not in _CLAIM_LEVELS:
            raise ValueError("promotion rule level is unsupported")
        rules[level] = {str(value) for value in row.get("required_evidence", [])}

    decisions: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ValueError("claims must contain objects")
        claim_id = str(claim.get("claim_id", f"claim-{index}"))
        requested_level = str(claim.get("requested_level", "candidate")).lower()
        if requested_level not in _CLAIM_LEVELS:
            raise ValueError("requested claim level is unsupported")
        evidence = {str(value) for value in claim.get("evidence_types", [])}
        unknown = sorted(evidence - set(_MECHANISM_STEPS) - {
            "field_consensus", "replicated_publication", "direct_experiment", "clinical_genetics",
            "database_phenotype", "preliminary_data", "public_reanalysis", "biological_inference", "candidate", "hypothesis",
        })
        if unknown:
            findings.append(_finding("unknown-evidence-type", "major", claim_id, "声明包含未登记的证据类型。", evidence_types=unknown))
        required = set(rules.get(requested_level, set()))
        association_supported = bool(evidence & {"coexpression", "spatial_colocalization", "replicated_publication", "database_phenotype", "clinical_genetics"})
        if requested_level == "association" and association_supported:
            required = set()
        missing = sorted(required - evidence)
        allowed_level = "candidate"
        if association_supported:
            allowed_level = "association"
        if {"direct_experiment", "phenotype_link"} <= evidence:
            allowed_level = "function"
        for level in ("substrate", "mechanism", "causal"):
            if set(rules[level]) <= evidence:
                allowed_level = level
        blocked = bool(missing) or _CLAIM_LEVELS[requested_level] > _CLAIM_LEVELS[allowed_level]
        if blocked:
            findings.append(_finding(
                "mechanism-claim-exceeds-evidence", "major", claim_id,
                f"当前证据最多支持“{allowed_level}”级别，不能提升为“{requested_level}”。",
                missing_evidence=missing,
                section=str(claim.get("section", "unknown")),
            ))
        decisions.append({
            "claim_id": claim_id,
            "entity": claim.get("entity"),
            "section": claim.get("section"),
            "requested_level": requested_level,
            "maximum_supported_level": allowed_level,
            "promotion_allowed": not blocked,
            "missing_evidence": missing,
        })
    major_count = sum(item["severity"] == "major" for item in findings)
    return {
        "decisions": decisions,
        "findings": findings,
        "major_finding_count": major_count,
        "all_claims_within_evidence": major_count == 0,
        "mechanistic_sequence": list(_MECHANISM_STEPS),
        "input_digest": _digest({"claims": claims, "promotion_rules": promotion_rules or []}),
    }


def _docx_paragraphs(payload: bytes) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("input is not a readable DOCX package") from exc
    names = set(archive.namelist())
    if "word/document.xml" not in names:
        raise ValueError("DOCX package lacks word/document.xml")
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    }
    root = ET.fromstring(archive.read("word/document.xml"))
    section = root.find(".//w:body/w:sectPr", ns)
    text_area_width_mm: float | None = None
    if section is not None:
        page_size = section.find("./w:pgSz", ns)
        page_margin = section.find("./w:pgMar", ns)
        if page_size is not None and page_margin is not None:
            try:
                page_width = int(page_size.attrib.get(f"{{{ns['w']}}}w", "0"))
                left_margin = int(page_margin.attrib.get(f"{{{ns['w']}}}left", "0"))
                right_margin = int(page_margin.attrib.get(f"{{{ns['w']}}}right", "0"))
                if page_width > left_margin + right_margin:
                    text_area_width_mm = round((page_width - left_margin - right_margin) / 56.692913386, 3)
            except ValueError:
                text_area_width_mm = None
    paragraphs: list[dict[str, Any]] = []
    for paragraph in root.findall(".//w:body/w:p", ns):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        raw_text = "".join(texts)
        text = raw_text.strip()
        properties = paragraph.find("./w:pPr", ns)
        style = paragraph.find("./w:pPr/w:pStyle", ns)
        style_id = style.attrib.get(f"{{{ns['w']}}}val", "") if style is not None else ""
        alignment_node = paragraph.find("./w:pPr/w:jc", ns)
        alignment = alignment_node.attrib.get(f"{{{ns['w']}}}val", "") if alignment_node is not None else ""
        indentation_node = paragraph.find("./w:pPr/w:ind", ns)
        indentation_twips: dict[str, int] = {}
        if indentation_node is not None:
            for key in ("left", "right", "firstLine", "hanging"):
                value = indentation_node.attrib.get(f"{{{ns['w']}}}{key}")
                if value is not None:
                    try:
                        indentation_twips[key] = int(value)
                    except ValueError:
                        indentation_twips[key] = -1
        runs = []
        for run in paragraph.findall("./w:r", ns):
            run_text = "".join(node.text or "" for node in run.findall(".//w:t", ns))
            if not run_text:
                continue
            properties = run.find("./w:rPr", ns)
            color = ""
            font = ""
            size = ""
            italic = False
            if properties is not None:
                color_node = properties.find("./w:color", ns)
                font_node = properties.find("./w:rFonts", ns)
                size_node = properties.find("./w:sz", ns)
                italic = properties.find("./w:i", ns) is not None
                if color_node is not None:
                    color = color_node.attrib.get(f"{{{ns['w']}}}val", "")
                if font_node is not None:
                    font = font_node.attrib.get(f"{{{ns['w']}}}eastAsia", "") or font_node.attrib.get(f"{{{ns['w']}}}ascii", "")
                if size_node is not None:
                    size = size_node.attrib.get(f"{{{ns['w']}}}val", "")
            runs.append({"text": run_text, "font": font, "color": color, "size_half_points": size, "italic": italic})
        extents = []
        for extent in paragraph.findall(".//wp:extent", ns):
            try:
                extents.append({
                    "width_mm": round(int(extent.attrib.get("cx", "0")) / 36000, 3),
                    "height_mm": round(int(extent.attrib.get("cy", "0")) / 36000, 3),
                })
            except ValueError:
                continue
        paragraphs.append({
            "text": text,
            "raw_text": raw_text,
            "style_id": style_id,
            "paragraph_alignment": alignment,
            "paragraph_indentation_twips": indentation_twips,
            "tab_count": len(paragraph.findall(".//w:tab", ns)),
            "empty_non_drawing_run_count": sum(
                1 for run in paragraph.findall("./w:r", ns)
                if run.find(".//w:drawing", ns) is None
                and not "".join(node.text or "" for node in run.findall(".//w:t", ns))
            ),
            "text_area_width_mm": text_area_width_mm,
            "runs": runs,
            "drawing_count": len(paragraph.findall(".//w:drawing", ns)),
            "drawing_extents": extents,
        })
    media = {name: archive.read(name) for name in names if name.startswith("word/media/")}
    return paragraphs, media


def _citation_numbers(text: str) -> list[int]:
    values: list[int] = []
    for match in _NUMERIC_CITATION.finditer(text):
        token = match.group(1).replace("，", ",").replace("；", ";")
        for part in re.split(r"[,;]", token):
            part = part.strip()
            range_match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
            if range_match:
                start, end = map(int, range_match.groups())
                if start <= end and end - start <= 100:
                    values.extend(range(start, end + 1))
            elif part.isdigit():
                values.append(int(part))
    return values


def _canonical_citation_marker(numbers: list[int]) -> str:
    """Format one citation group with compact commas and en-dash ranges."""
    if not numbers:
        return "[]"
    ordered = list(dict.fromkeys(numbers))
    parts: list[str] = []
    start = previous = ordered[0]
    for number in ordered[1:] + [None]:
        if number is not None and number == previous + 1:
            previous = number
            continue
        parts.append(str(start) if start == previous else f"{start}–{previous}")
        if number is not None:
            start = previous = number
    return "[" + ",".join(parts) + "]"


def _renumber_docx_payload(payload: bytes, renumber_map: dict[int, int]) -> bytes:
    """Create a separate DOCX copy when every citation marker is run-local."""
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    root = ET.fromstring(members["word/document.xml"])
    for paragraph in root.findall(f".//{{{w_ns}}}p"):
        nodes = paragraph.findall(f".//{{{w_ns}}}t")
        combined = "".join(node.text or "" for node in nodes)
        combined_count = len(_NUMERIC_CITATION.findall(combined))
        node_count = sum(len(_NUMERIC_CITATION.findall(node.text or "")) for node in nodes)
        if combined_count != node_count:
            raise ValueError("a citation marker is split across DOCX runs and cannot be safely renumbered")
        for node in nodes:
            value = node.text or ""
            def replace_marker(match: re.Match[str]) -> str:
                numbers = _citation_numbers(match.group(0))
                mapped = [renumber_map.get(number, number) for number in numbers]
                return "[" + ",".join(str(number) for number in mapped) + "]"
            node.text = _NUMERIC_CITATION.sub(replace_marker, value)
    body = root.find(f".//{{{w_ns}}}body")
    if body is not None:
        children = list(body)
        reference_heading_index = None
        for index, child in enumerate(children):
            if child.tag != f"{{{w_ns}}}p":
                continue
            text = "".join(node.text or "" for node in child.findall(f".//{{{w_ns}}}t")).strip()
            if _normalize_section_name(text) == "references":
                reference_heading_index = index
                break
        if reference_heading_index is not None:
            numbered: list[tuple[int, ET.Element]] = []
            for child in children[reference_heading_index + 1:]:
                if child.tag != f"{{{w_ns}}}p":
                    continue
                text = "".join(node.text or "" for node in child.findall(f".//{{{w_ns}}}t")).strip()
                match = _REFERENCE_LABEL.match(text)
                if match:
                    numbered.append((int(match.group(1)), child))
            if numbered:
                insertion_index = min(list(body).index(child) for _number, child in numbered)
                for _number, child in numbered:
                    body.remove(child)
                for offset, (_number, child) in enumerate(sorted(numbered, key=lambda item: item[0])):
                    body.insert(insertion_index + offset, child)
    members["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, member in members.items():
            target.writestr(name, member)
    return output.getvalue()


def audit_docx_proposal_delivery(
    docx_path: str | None = None,
    docx_payload_base64: str | None = None,
    document_model: list[dict[str, Any]] | None = None,
    abstract_heading_terms: list[str] | None = None,
    reference_heading_terms: list[str] | None = None,
    rendered_pages: list[dict[str, Any]] | None = None,
    renumber_citations: bool = False,
    style_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read a DOCX package and audit citation reciprocity, styles, and render evidence."""
    source_count = sum(value is not None for value in (docx_path, docx_payload_base64, document_model))
    if source_count != 1:
        raise ValueError("provide exactly one of docx_path, docx_payload_base64, or document_model")
    source_payload: bytes | None = None
    if docx_path is not None:
        path = Path(docx_path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".docx":
            raise ValueError("docx_path must identify a readable .docx file")
        payload = path.read_bytes()
        source_payload = payload
        paragraphs, media = _docx_paragraphs(payload)
        source_digest = hashlib.sha256(payload).hexdigest()
    elif docx_payload_base64 is not None:
        try:
            payload = base64.b64decode(docx_payload_base64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("docx_payload_base64 is invalid") from exc
        paragraphs, media = _docx_paragraphs(payload)
        source_payload = payload
        source_digest = hashlib.sha256(payload).hexdigest()
    else:
        if not isinstance(document_model, list) or not document_model:
            raise ValueError("document_model must be a nonempty paragraph array")
        paragraphs = [dict(value) for value in document_model]
        media = {}
        source_digest = _digest(document_model)

    abstract_headings = {value.lower() for value in (abstract_heading_terms or ["中文摘要", "摘要", "abstract"])}
    reference_headings = {value.lower() for value in (reference_heading_terms or ["参考文献", "主要参考文献", "references"])}
    section = "body"
    body_texts: list[str] = []
    abstract_texts: list[str] = []
    reference_rows: list[tuple[int, str]] = []
    style_signatures: Counter[tuple[str, str, str]] = Counter()
    caption_numbers: dict[str, list[int]] = {"figure": [], "table": []}
    findings: list[dict[str, Any]] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        text = str(paragraph.get("text", "")).strip()
        lowered = re.sub(r"[\s：:]+", "", text).lower()
        if lowered in {re.sub(r"[\s：:]+", "", value).lower() for value in abstract_headings}:
            section = "abstract"
            continue
        if lowered in {re.sub(r"[\s：:]+", "", value).lower() for value in reference_headings}:
            section = "references"
            continue
        if _normalize_section_name(text) not in {"unclassified", "abstract_cn", "abstract_en", "references"}:
            section = "body"
            continue
        if section == "abstract":
            abstract_texts.append(text)
        elif section == "references":
            match = _REFERENCE_LABEL.match(text)
            if match:
                reference_rows.append((int(match.group(1)), text))
        else:
            body_texts.append(text)
        caption_match = re.match(r"^(图|表|figure|fig\.|table)\s*([0-9]+)", text, re.IGNORECASE)
        if caption_match:
            kind = "table" if caption_match.group(1).lower() in {"表", "table"} else "figure"
            caption_numbers[kind].append(int(caption_match.group(2)))
        for run in paragraph.get("runs", []):
            if str(run.get("text", "")).strip():
                style_signatures[(str(run.get("font", "")), str(run.get("size_half_points", "")), str(run.get("color", "")))] += len(str(run.get("text", "")))

    def is_caption(paragraph: dict[str, Any]) -> bool:
        text = str(paragraph.get("text", "")).strip()
        style = str(paragraph.get("style_id", "")).lower()
        return "caption" in style or bool(re.match(r"^(?:图|表|figure|fig\.|table)\s*[A-Za-z0-9一二三四五六七八九十]", text, re.IGNORECASE))

    for index, paragraph in enumerate(paragraphs):
        if int(paragraph.get("drawing_count", 0)) <= 0:
            continue
        adjacent = []
        if index > 0:
            adjacent.append(paragraphs[index - 1])
        if index + 1 < len(paragraphs):
            adjacent.append(paragraphs[index + 1])
        if not any(is_caption(item) for item in adjacent):
            findings.append(_finding("figure-caption-not-adjacent", "major", f"paragraph:{index+1}", "嵌入图件前后未识别到相邻图题或表题。"))
        if paragraph.get("paragraph_alignment") != "center":
            findings.append(_finding("figure-paragraph-not-centered", "major", f"paragraph:{index+1}", "图件所在 Word 段落未显式居中。"))
        if (
            str(paragraph.get("raw_text", "")) != ""
            or int(paragraph.get("tab_count", 0)) > 0
            or int(paragraph.get("empty_non_drawing_run_count", 0)) > 0
            or any(int(value) != 0 for value in dict(paragraph.get("paragraph_indentation_twips") or {}).values())
        ):
            findings.append(_finding("figure-paragraph-placeholder-present", "major", f"paragraph:{index+1}", "图件所在段落含文字、空格、制表符或非零缩进占位。"))
        text_width = paragraph.get("text_area_width_mm")
        for extent in paragraph.get("drawing_extents", []):
            if extent.get("width_mm", 0) <= 0 or extent.get("height_mm", 0) <= 0:
                findings.append(_finding("figure-size-invalid", "major", f"paragraph:{index+1}", "嵌入图件缺少有效的 Word 版面尺寸。"))
            if not isinstance(text_width, (int, float)) or float(extent.get("width_mm", 0)) > float(text_width):
                findings.append(_finding("figure-exceeds-text-boundary", "major", f"paragraph:{index+1}", "嵌入图件宽度超过正文版心，或无法从 Word 页面设置核实正文宽度。", figure_width_mm=extent.get("width_mm"), text_area_width_mm=text_width))

    for kind, sequence in caption_numbers.items():
        if sequence and sequence != list(range(1, len(sequence) + 1)):
            findings.append(_finding("caption-numbering-not-continuous", "major", kind, "图题或表题编号不连续。", observed=sequence))

    body_text = "\n".join(body_texts)
    abstract_text = "\n".join(abstract_texts)
    citations = _citation_numbers(body_text)
    abstract_citations = _citation_numbers(abstract_text)
    refs = [number for number, _text in reference_rows]
    citation_markers = _NUMERIC_CITATION.findall(body_text)
    raw_markers = [match.group(0) for match in _NUMERIC_CITATION.finditer(body_text)]
    noncanonical_markers = [marker for marker in raw_markers if marker != _canonical_citation_marker(_citation_numbers(marker))]
    if noncanonical_markers:
        findings.append(_finding(
            "citation-marker-format-inconsistent", "minor", "body",
            "正文编号引文的空格、分隔符或范围连接号不统一。",
            observed=noncanonical_markers[:20],
        ))
    if abstract_citations:
        findings.append(_finding("abstract-citation-present", "major", "abstract", "摘要中存在编号式文献引用。", citation_numbers=sorted(set(abstract_citations))))
    unique_first_order = list(dict.fromkeys(citations))
    expected_order = list(range(1, len(unique_first_order) + 1))
    renumber_map = {old: new for new, old in enumerate(unique_first_order, start=1)}
    if unique_first_order != expected_order:
        findings.append(_finding("citation-first-appearance-order", "major", "body", "正文引文未按首次出现顺序连续编号。", observed=unique_first_order, renumber_map=renumber_map))
    if len(refs) != len(set(refs)):
        findings.append(_finding("duplicate-reference-number", "major", "references", "参考文献表存在重复编号。"))
    missing_references = sorted(set(citations) - set(refs))
    unused_references = sorted(set(refs) - set(citations))
    if missing_references:
        findings.append(_finding("citation-without-reference", "major", "references", "正文引文在参考文献表中没有对应条目。", numbers=missing_references))
    if unused_references:
        findings.append(_finding("reference-not-cited", "major", "references", "参考文献表条目未在正文中引用。", numbers=unused_references))
    if refs and refs != list(range(1, len(refs) + 1)):
        findings.append(_finding("reference-list-not-continuous", "major", "references", "参考文献表编号不连续或顺序异常。", observed=refs))

    total_styled_characters = sum(style_signatures.values())
    dominant_style = style_signatures.most_common(1)[0][0] if style_signatures else None
    minor_style_characters = total_styled_characters - (style_signatures.most_common(1)[0][1] if style_signatures else 0)
    if total_styled_characters and minor_style_characters / total_styled_characters > 0.2:
        findings.append(_finding("body-style-fragmentation", "minor", "styles", "正文存在较大比例的字体、字号或颜色样式分裂，需要结合标题、图注和强调语义人工复核。", dominant_style=dominant_style))

    style_policy = dict(style_policy or {})
    if not style_policy:
        findings.append(_finding("document-style-policy-missing", "major", "style_policy", "尚未从当前官方模板登记正文、标题、图题和参考文献的样式要求。"))
    else:
        allowed_fonts = {str(value) for value in style_policy.get("allowed_fonts", []) if str(value)}
        minimum_size = style_policy.get("minimum_size_half_points")
        allowed_colors = {str(value).upper() for value in style_policy.get("allowed_colors", []) if str(value)}
        for font, size, color in style_signatures:
            if allowed_fonts and font and font not in allowed_fonts:
                findings.append(_finding("font-outside-template-policy", "major", "styles", "检测到不在当前模板样式规则中的字体。", font=font))
            if isinstance(minimum_size, int) and size.isdigit() and int(size) < minimum_size:
                findings.append(_finding("text-below-template-minimum", "major", "styles", "检测到小于模板允许最小字号的文字。", size_half_points=int(size)))
            if allowed_colors and color and color.upper() not in allowed_colors:
                findings.append(_finding("color-outside-template-policy", "major", "styles", "检测到不在当前模板样式规则中的文字颜色。", color=color))

    rendered_pages = list(rendered_pages or [])
    if not rendered_pages:
        findings.append(_finding("rendered-page-review-missing", "major", "render", "尚未登记逐页渲染和人工视觉复核，不能认定 Word 交付版式完成。"))
    else:
        page_numbers = [page.get("page_number") for page in rendered_pages]
        if page_numbers != list(range(1, len(rendered_pages) + 1)):
            findings.append(_finding("rendered-page-sequence-invalid", "major", "render", "逐页渲染记录缺页、重复或顺序异常。", observed=page_numbers))
        for page in rendered_pages:
            page_number = page.get("page_number")
            if not page.get("image_sha256") or page.get("reviewed") is not True:
                findings.append(_finding("rendered-page-unreviewed", "major", f"page:{page_number}", "该页缺少图像校验值或人工视觉复核。"))
            for field in (
                "clipping_free", "overlap_free", "legible", "figure_final_size_checked",
                "page_breaks_reviewed", "caption_figure_same_page", "figures_within_text_width",
                "figure_paragraphs_centered", "figure_paragraphs_placeholder_free",
            ):
                if page.get(field) is not True:
                    findings.append(_finding("rendered-page-quality-failed", "major", f"page:{page_number}", f"逐页视觉复核未确认 {field}。"))

    renumbered_payload = b""
    if renumber_citations:
        if source_payload is None:
            findings.append(_finding("native-docx-required-for-renumbering", "major", "renumber_citations", "自动重编号需要原生 DOCX 输入，文档模型只生成修改映射。"))
        elif abstract_citations or missing_references or len(refs) != len(set(refs)):
            findings.append(_finding("citation-renumbering-preconditions-failed", "major", "renumber_citations", "摘要引文、缺失条目或重复编号尚未解决，不能安全生成重编号副本。"))
        else:
            try:
                renumbered_payload = _renumber_docx_payload(source_payload, renumber_map)
            except ValueError as exc:
                findings.append(_finding("citation-marker-split-across-runs", "major", "renumber_citations", str(exc)))

    major_count = sum(item["severity"] == "major" for item in findings)
    return {
        "source_sha256": source_digest,
        "paragraph_count": len(paragraphs),
        "embedded_media_count": len(media),
        "citation_sequence": unique_first_order,
        "reference_sequence": refs,
        "citation_renumber_map": {str(key): value for key, value in renumber_map.items()},
        "missing_reference_numbers": missing_references,
        "unused_reference_numbers": unused_references,
        "style_summary": {
            "signature_count": len(style_signatures),
            "dominant_style": dominant_style,
            "styled_character_count": total_styled_characters,
        },
        "caption_sequences": caption_numbers,
        "citation_marker_count": len(citation_markers),
        "rendered_page_count": len(rendered_pages),
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_submission_delivery": major_count == 0,
        "renumbered_docx_base64": base64.b64encode(renumbered_payload).decode("ascii") if renumbered_payload else "",
        "renumbered_docx_sha256": hashlib.sha256(renumbered_payload).hexdigest() if renumbered_payload else "",
        "limitations": [
            "结构化检查不会自动判断科学内容质量；最终 Word 版本必须逐页渲染并由人员检查断页、遮挡、图表清晰度和标题层级。",
            "编号修正映射只用于生成明确的修改计划；本函数不会覆盖原始 DOCX。",
        ],
    }
