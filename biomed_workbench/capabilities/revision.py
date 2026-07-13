"""Deterministic manuscript revision lineage and reviewer-commitment gates."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import date
from typing import Any


_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
_SEMVER_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?$")
_BLOCK_ID_RE = re.compile(r"^B(0*[1-9][0-9]*)$")
_MARKER_RE = re.compile(r"<!--\s*block\s*:", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\b(?:AUTHOR_INPUT_NEEDED|TODO|TBD|PLACEHOLDER)\b|\[[^\]]*(?:insert|provide|confirm)[^\]]*\]", re.IGNORECASE)
_BLOCK_KINDS = {"heading", "paragraph", "list", "table", "blockquote", "code", "caption", "equation"}
_OPS = {"replace_block", "insert_after", "delete_block"}
_ACTIONS = {
    "ACCEPT_TEXT", "ACCEPT_ANALYSIS", "ACCEPT_EXPERIMENT", "ACCEPT_FIGURE", "CLARIFY_EXISTING",
    "ADD_CITATION", "SOFTEN_CLAIM", "PARTIAL", "DISAGREE", "OUT_OF_SCOPE",
    "AUTHOR_INPUT_NEEDED", "BLOCKING",
}
_READINESS = {"ready_to_submit", "draft_with_placeholders", "needs_author_input", "blocked"}
_RISKS = {"low", "medium", "high", "blocking"}
_STATUSES = {"completed", "partial", "unresolved", "blocked", "disputed"}
_EVIDENCE_ACTIONS = {"ACCEPT_ANALYSIS", "ACCEPT_EXPERIMENT", "ACCEPT_FIGURE", "ADD_CITATION"}
_CHANGE_ACTIONS = {"ACCEPT_TEXT", "ACCEPT_ANALYSIS", "ACCEPT_EXPERIMENT", "ACCEPT_FIGURE", "ADD_CITATION", "SOFTEN_CLAIM", "PARTIAL", "OUT_OF_SCOPE"}


def _exact(value: Any, fields: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{location} must contain exactly {sorted(fields)}")
    return value


def _identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not _ID_RE.fullmatch(value):
        raise ValueError(f"{location} must be a normalized safe identifier")
    return value


def _text(value: Any, location: str, *, maximum: int = 200000, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{location} must be text within the size limit")
    if not allow_empty and not value.strip():
        raise ValueError(f"{location} must be meaningful text")
    return value


def _strings(value: Any, location: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{location} must be a {'possibly empty ' if allow_empty else 'nonempty '}list")
    result = [_identifier(item, f"{location} item") for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{location} contains duplicate IDs")
    return result


def _sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manuscript_block_hash(kind: str, text: str) -> str:
    """Return the exact-content hash used by revision manifests."""
    if kind not in _BLOCK_KINDS:
        raise ValueError("unsupported manuscript block kind")
    _text(text, "block text")
    return _sha256({"kind": kind, "text": text})


def build_revision_base(document_id: str, version_id: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a machine-generated revision base from ordered manuscript blocks."""
    _identifier(document_id, "document_id")
    _identifier(version_id, "version_id")
    if not isinstance(blocks, list) or not blocks or len(blocks) > 100000:
        raise ValueError("blocks must contain 1 to 100000 records")
    prepared = []
    explicit_ids: set[str] = set()
    maximum = 0
    for index, raw in enumerate(blocks, start=1):
        block = _exact(raw, {"id", "kind", "text"}, f"block {index}")
        if block["id"] is not None:
            block_id = _identifier(block["id"], f"block {index}.id")
            match = _BLOCK_ID_RE.fullmatch(block_id)
            if not match:
                raise ValueError("machine manuscript block IDs must use B followed by a positive integer")
            if block_id in explicit_ids:
                raise ValueError("manuscript block IDs must be unique")
            explicit_ids.add(block_id)
            maximum = max(maximum, int(match.group(1)))
        prepared.append(block)
    normalized: list[dict[str, str]] = []
    ids = set(explicit_ids)
    next_number = maximum + 1
    for index, block in enumerate(prepared, start=1):
        block_id = block["id"]
        if block_id is None:
            block_id = f"B{next_number:05d}"
            next_number += 1
            ids.add(block_id)
        kind = block["kind"]
        if kind not in _BLOCK_KINDS:
            raise ValueError(f"block {block_id} has unsupported kind")
        text = _text(block["text"], f"block {block_id}.text")
        if _MARKER_RE.search(text):
            raise ValueError("manuscript block text must not contain working block markers")
        normalized.append({"id": block_id, "kind": kind, "text": text, "hash": manuscript_block_hash(kind, text)})
    body = {"document_id": document_id, "version_id": version_id, "blocks": normalized}
    return {**body, "document_hash": _sha256(body)}


def _validate_base(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]], int]:
    base = _exact(raw, {"document_id", "version_id", "document_hash", "blocks"}, "base_document")
    _identifier(base["document_id"], "base_document.document_id")
    _identifier(base["version_id"], "base_document.version_id")
    if not isinstance(base["document_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", base["document_hash"]):
        raise ValueError("base_document.document_hash must be a full lowercase SHA-256 digest")
    if not isinstance(base["blocks"], list) or not 1 <= len(base["blocks"]) <= 100000:
        raise ValueError("base_document.blocks must contain 1 to 100000 records")
    index: dict[str, dict[str, Any]] = {}
    maximum = 0
    normalized = []
    for position, raw_block in enumerate(base["blocks"], start=1):
        block = _exact(raw_block, {"id", "kind", "text", "hash"}, f"base block {position}")
        block_id = _identifier(block["id"], f"base block {position}.id")
        match = _BLOCK_ID_RE.fullmatch(block_id)
        if not match or block_id in index:
            raise ValueError("base block IDs must be unique machine IDs")
        maximum = max(maximum, int(match.group(1)))
        if block["kind"] not in _BLOCK_KINDS:
            raise ValueError(f"base block {block_id} has unsupported kind")
        text = _text(block["text"], f"base block {block_id}.text")
        if _MARKER_RE.search(text):
            raise ValueError("base block text must not contain working block markers")
        expected = manuscript_block_hash(block["kind"], text)
        if block["hash"] != expected:
            raise ValueError(f"base block {block_id} hash is stale or fabricated")
        clean = {"id": block_id, "kind": block["kind"], "text": text, "hash": expected}
        normalized.append(clean)
        index[block_id] = clean
    body = {"document_id": base["document_id"], "version_id": base["version_id"], "blocks": normalized}
    if base["document_hash"] != _sha256(body):
        raise ValueError("base document hash is stale or fabricated")
    return {**body, "document_hash": base["document_hash"]}, index, maximum


def _issue(code: str, severity: str, subject_ids: list[str], message: str, action: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "subject_ids": sorted(set(subject_ids)), "message": message, "action": action}


def apply_manuscript_revision(
    base_document: dict[str, Any],
    patch: dict[str, Any],
    review_items: list[dict[str, Any]],
    policy: dict[str, Any],
    audit_provenance: dict[str, Any],
) -> dict[str, Any]:
    """Validate and atomically reduce a block patch into a new revision artifact."""
    base, base_index, maximum = _validate_base(base_document)
    patch = _exact(patch, {"patch_id", "revision_round", "base_document_hash", "operations", "emitted_by"}, "patch")
    patch_id = _identifier(patch["patch_id"], "patch.patch_id")
    _identifier(patch["emitted_by"], "patch.emitted_by")
    if not isinstance(patch["revision_round"], int) or isinstance(patch["revision_round"], bool) or patch["revision_round"] <= 0:
        raise ValueError("patch.revision_round must be a positive integer")
    if patch["base_document_hash"] != base["document_hash"]:
        raise ValueError("patch is not bound to the current base document")
    if not isinstance(patch["operations"], list) or not 1 <= len(patch["operations"]) <= 100000:
        raise ValueError("patch.operations must contain 1 to 100000 records")
    policy = _exact(policy, {"structural_acknowledged", "touched_ratio_threshold", "terminal_policy", "editor_priority_comment_ids"}, "policy")
    if not isinstance(policy["structural_acknowledged"], bool) or policy["terminal_policy"] not in {"advisory", "strict"}:
        raise ValueError("policy flags are invalid")
    threshold = policy["touched_ratio_threshold"]
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("policy.touched_ratio_threshold must be a finite ratio in [0, 1]")
    priority_ids = _strings(policy["editor_priority_comment_ids"], "policy.editor_priority_comment_ids", allow_empty=True)
    provenance = _exact(audit_provenance, {"audit_id", "audit_version", "reviewed_at", "independent_from_writer", "comment_extraction_complete"}, "audit_provenance")
    _identifier(provenance["audit_id"], "audit_provenance.audit_id")
    if not isinstance(provenance["audit_version"], str) or not _SEMVER_RE.fullmatch(provenance["audit_version"]):
        raise ValueError("audit_provenance.audit_version must be semantic version text")
    try:
        date.fromisoformat(provenance["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("audit_provenance.reviewed_at must be an ISO date") from exc
    if not isinstance(provenance["independent_from_writer"], bool) or not isinstance(provenance["comment_extraction_complete"], bool):
        raise ValueError("audit provenance completion flags must be boolean")

    if not isinstance(review_items, list) or not 1 <= len(review_items) <= 100000:
        raise ValueError("review_items must contain 1 to 100000 records")
    review_index: dict[str, dict[str, Any]] = {}
    review_fields = {"id", "reviewer", "comment", "action", "readiness", "risk_level", "manuscript_block_ids", "evidence_ids", "response_text", "status", "conflicting_with"}
    for position, raw in enumerate(review_items, start=1):
        item = _exact(raw, review_fields, f"review item {position}")
        item_id = _identifier(item["id"], f"review item {position}.id")
        if item_id in review_index:
            raise ValueError("review item IDs must be unique")
        _text(item["reviewer"], f"review item {item_id}.reviewer", maximum=1000)
        _text(item["comment"], f"review item {item_id}.comment", maximum=50000)
        _text(item["response_text"], f"review item {item_id}.response_text", maximum=50000)
        if item["action"] not in _ACTIONS or item["readiness"] not in _READINESS or item["risk_level"] not in _RISKS or item["status"] not in _STATUSES:
            raise ValueError(f"review item {item_id} has unsupported action, readiness, risk, or status")
        normalized = dict(item)
        normalized["manuscript_block_ids"] = _strings(item["manuscript_block_ids"], f"review item {item_id}.manuscript_block_ids", allow_empty=True)
        normalized["evidence_ids"] = _strings(item["evidence_ids"], f"review item {item_id}.evidence_ids", allow_empty=True)
        normalized["conflicting_with"] = _strings(item["conflicting_with"], f"review item {item_id}.conflicting_with", allow_empty=True)
        review_index[item_id] = normalized
    unknown_priorities = sorted(set(priority_ids) - set(review_index))
    if unknown_priorities:
        raise ValueError("editor priority list references unknown review items")
    for item_id, item in review_index.items():
        unknown = sorted(set(item["conflicting_with"]) - set(review_index))
        if item_id in item["conflicting_with"] or unknown:
            raise ValueError(f"review item {item_id} has invalid conflict references")

    analyses = []
    op_ids: set[str] = set()
    targets: set[str] = set()
    bound_comments: set[str] = set()
    changed_existing: set[str] = set()
    heading_op_ids: list[str] = []
    inserted_heading_count = deleted_heading_count = 0
    for position, raw in enumerate(patch["operations"], start=1):
        op = _exact(raw, {"op_id", "op", "target_block_id", "expected_block_hash", "new_blocks", "comment_ids", "roadmap_item_ids", "rationale"}, f"operation {position}")
        op_id = _identifier(op["op_id"], f"operation {position}.op_id")
        if op_id in op_ids:
            raise ValueError("operation IDs must be unique")
        op_ids.add(op_id)
        if op["op"] not in _OPS:
            raise ValueError(f"operation {op_id} is unsupported")
        target = op["target_block_id"]
        if target != "DOC-BODY-START":
            _identifier(target, f"operation {op_id}.target_block_id")
        if target in targets:
            raise ValueError("a base block may be targeted by only one operation")
        targets.add(target)
        if target == "DOC-BODY-START":
            if op["op"] != "insert_after" or op["expected_block_hash"] is not None:
                raise ValueError("DOC-BODY-START supports insert_after with a null expected hash only")
            target_block = None
        else:
            target_block = base_index.get(target)
            if target_block is None:
                raise ValueError(f"operation {op_id} targets an unknown base block")
            if op["expected_block_hash"] != target_block["hash"]:
                raise ValueError(f"operation {op_id} has a stale or fabricated expected block hash")
            changed_existing.add(target)
        comment_ids = _strings(op["comment_ids"], f"operation {op_id}.comment_ids")
        roadmap_ids = _strings(op["roadmap_item_ids"], f"operation {op_id}.roadmap_item_ids")
        unknown_comments = sorted(set(comment_ids) - set(review_index))
        if unknown_comments:
            raise ValueError(f"operation {op_id} references unknown review items")
        bound_comments.update(comment_ids)
        _text(op["rationale"], f"operation {op_id}.rationale", maximum=10000)
        new_blocks = op["new_blocks"]
        if not isinstance(new_blocks, list):
            raise ValueError(f"operation {op_id}.new_blocks must be a list")
        if op["op"] == "delete_block" and new_blocks:
            raise ValueError("delete_block cannot carry new blocks")
        if op["op"] != "delete_block" and not new_blocks:
            raise ValueError(f"operation {op_id} requires at least one new block")
        normalized_new = []
        for block_position, raw_new in enumerate(new_blocks, start=1):
            new = _exact(raw_new, {"kind", "text"}, f"operation {op_id} new block {block_position}")
            if new["kind"] not in _BLOCK_KINDS:
                raise ValueError(f"operation {op_id} has an unsupported new block kind")
            new_text = _text(new["text"], f"operation {op_id} new block {block_position}.text")
            if _MARKER_RE.search(new_text):
                raise ValueError("patch content must not contain working block markers")
            normalized_new.append({"kind": new["kind"], "text": new_text})
        old_heading = target_block is not None and target_block["kind"] == "heading"
        new_headings = sum(block["kind"] == "heading" for block in normalized_new)
        if old_heading or new_headings:
            heading_op_ids.append(op_id)
        if op["op"] == "delete_block" and old_heading:
            deleted_heading_count += 1
        elif op["op"] == "replace_block":
            deleted_heading_count += int(old_heading)
            inserted_heading_count += new_headings
        else:
            inserted_heading_count += new_headings
        analyses.append({**op, "comment_ids": comment_ids, "roadmap_item_ids": roadmap_ids, "new_blocks": normalized_new})

    touched_ratio = len(changed_existing) / len(base["blocks"])
    heading_delta = inserted_heading_count - deleted_heading_count
    structural_flags = {
        "heading_operation_ids": heading_op_ids,
        "heading_count_delta": heading_delta,
        "touched_ratio": round(touched_ratio, 6),
        "touched_ratio_threshold": float(threshold),
        "touched_ratio_exceeded": touched_ratio > threshold,
        "any": bool(heading_op_ids) or heading_delta != 0 or touched_ratio > threshold,
        "acknowledged": policy["structural_acknowledged"],
    }
    issues: list[dict[str, Any]] = []
    if structural_flags["any"] and not policy["structural_acknowledged"]:
        issues.append(_issue("STRUCTURAL_CHANGE_UNACKNOWLEDGED", "major", heading_op_ids or sorted(changed_existing), "The patch changes manuscript structure or exceeds the declared touched-block threshold without an explicit checkpoint.", "Review the structural diff and explicitly acknowledge it before applying the patch."))
    if not provenance["independent_from_writer"]:
        issues.append(_issue("REVISION_AUDIT_NOT_INDEPENDENT", "major", [provenance["audit_id"]], "The same writer is presented as the independent revision auditor.", "Use a separately declared audit pass before release."))
    if not provenance["comment_extraction_complete"]:
        issues.append(_issue("REVIEW_COMMENT_EXTRACTION_INCOMPLETE", "major", [provenance["audit_id"]], "Reviewer-comment extraction is incomplete, so response coverage cannot be proven.", "Complete and verify comment extraction before applying or releasing the revision."))

    for item_id, item in review_index.items():
        if item["action"] in {"AUTHOR_INPUT_NEEDED", "BLOCKING"} and item["status"] == "completed":
            issues.append(_issue("FALSE_COMPLETION_STATUS", "major", [item_id], "An author-input or blocking action cannot be marked completed.", "Correct the status and obtain the required facts or action."))
        if item["status"] != "completed" or item["readiness"] != "ready_to_submit":
            issues.append(_issue("REVIEW_COMMITMENT_UNRESOLVED", "major", [item_id], "The reviewer commitment is not both completed and ready to submit.", "Resolve the commitment or keep the revision package blocked."))
        if item["action"] in _EVIDENCE_ACTIONS and not item["evidence_ids"]:
            issues.append(_issue("CLAIMED_ACTION_LACKS_EVIDENCE", "major", [item_id], "A claimed analysis, experiment, figure, or citation has no supplied evidence identifier.", "Bind the response to the actual analysis, experiment, figure, or verified citation artifact."))
        if item["action"] in _CHANGE_ACTIONS and item_id not in bound_comments:
            issues.append(_issue("CLAIMED_CHANGE_NOT_PATCH_BOUND", "major", [item_id], "The response claims a manuscript change but no patch operation is bound to the comment.", "Bind the comment to the exact patch operation and resulting manuscript blocks."))
        if _PLACEHOLDER_RE.search(item["response_text"]):
            issues.append(_issue("RESPONSE_PLACEHOLDER_PRESENT", "major", [item_id], "The response contains an unresolved author-input placeholder.", "Replace the placeholder with supplied facts or retain a non-submittable readiness state."))
        for other in item["conflicting_with"]:
            if item_id not in review_index[other]["conflicting_with"]:
                issues.append(_issue("REVIEW_CONFLICT_ASYMMETRIC", "major", [item_id, other], "A reviewer-request conflict is not declared symmetrically.", "Record both sides of the conflict and reconcile them against editor priorities."))
            if item_id not in priority_ids and other not in priority_ids:
                issues.append(_issue("REVIEW_CONFLICT_UNRESOLVED", "major", [item_id, other], "Conflicting reviewer requests lack an explicit editor-priority resolution.", "Bind the balancing decision to an editor-priority comment or keep the package blocked."))

    blocking = any(issue["severity"] == "major" for issue in issues)
    apply_status = "refused_quality_gate" if blocking else "applied"
    revised_document = None
    operations_applied: list[dict[str, Any]] = []
    fresh_ids: list[str] = []
    pure_moves: list[dict[str, str]] = []
    untouched_ids = [block["id"] for block in base["blocks"] if block["id"] not in changed_existing]
    if not blocking:
        by_target = {op["target_block_id"]: op for op in analyses}

        def fresh(block: dict[str, str]) -> dict[str, str]:
            nonlocal maximum
            maximum += 1
            block_id = f"B{maximum:05d}"
            fresh_ids.append(block_id)
            return {"id": block_id, "kind": block["kind"], "text": block["text"], "hash": manuscript_block_hash(block["kind"], block["text"])}

        revised_blocks: list[dict[str, str]] = []
        start_op = by_target.get("DOC-BODY-START")
        if start_op:
            created = [fresh(block) for block in start_op["new_blocks"]]
            revised_blocks.extend(created)
            operations_applied.append({"op_id": start_op["op_id"], "op": start_op["op"], "target_block_id": "DOC-BODY-START", "result_block_ids": [item["id"] for item in created], "comment_ids": start_op["comment_ids"], "roadmap_item_ids": start_op["roadmap_item_ids"]})
        deleted_hashes = {base_index[op["target_block_id"]]["hash"]: op["target_block_id"] for op in analyses if op["op"] == "delete_block"}
        for block in base["blocks"]:
            op = by_target.get(block["id"])
            if op is None:
                revised_blocks.append(dict(block))
                continue
            if op["op"] == "delete_block":
                created = []
            elif op["op"] == "replace_block":
                head = op["new_blocks"][0]
                created = [{"id": block["id"], "kind": head["kind"], "text": head["text"], "hash": manuscript_block_hash(head["kind"], head["text"])}]
                created.extend(fresh(new) for new in op["new_blocks"][1:])
                revised_blocks.extend(created)
            else:
                revised_blocks.append(dict(block))
                created = [fresh(new) for new in op["new_blocks"]]
                revised_blocks.extend(created)
            for created_block in created:
                origin = deleted_hashes.get(created_block["hash"])
                if origin:
                    pure_moves.append({"from_block_id": origin, "to_block_id": created_block["id"]})
            operations_applied.append({"op_id": op["op_id"], "op": op["op"], "target_block_id": op["target_block_id"], "result_block_ids": [item["id"] for item in created], "comment_ids": op["comment_ids"], "roadmap_item_ids": op["roadmap_item_ids"]})
        revised_body = {"document_id": base["document_id"], "version_id": f"{base['version_id']}.r{patch['revision_round']}", "blocks": revised_blocks}
        revised_document = {**revised_body, "document_hash": _sha256(revised_body), "parent_document_hash": base["document_hash"], "revision_round": patch["revision_round"], "patch_id": patch_id}
        revised_ids = {block["id"] for block in revised_blocks}
        for item_id, item in review_index.items():
            unknown_blocks = sorted(set(item["manuscript_block_ids"]) - revised_ids)
            if unknown_blocks:
                issues.append(_issue("RESPONSE_LOCATION_UNRESOLVED", "major", [item_id, *unknown_blocks], "The response names manuscript blocks absent from the revised artifact.", "Update the response location binding to current revision block IDs."))
        if issues:
            revised_document = None
            operations_applied = []
            fresh_ids = []
            pure_moves = []
            apply_status = "refused_quality_gate"

    issue_counts = dict(sorted(Counter(issue["severity"] for issue in issues).items()))
    release_safe = apply_status == "applied" and not issues
    report_basis = {
        "patch_id": patch_id,
        "base_document_hash": base["document_hash"],
        "revision_round": patch["revision_round"],
        "apply_status": apply_status,
        "operations_applied": operations_applied,
        "issues": issues,
        "audit_id": provenance["audit_id"],
    }
    return {
        "apply_status": apply_status,
        "release_safe": release_safe,
        "base_document_hash": base["document_hash"],
        "revised_document": revised_document,
        "operations_applied": operations_applied,
        "fresh_block_ids": fresh_ids,
        "untouched_block_ids": untouched_ids,
        "pure_move_pairs": pure_moves,
        "structural_flags": structural_flags,
        "review_coverage": {
            "comment_count": len(review_index),
            "patch_bound_comment_ids": sorted(bound_comments),
            "unbound_comment_ids": sorted(set(review_index) - bound_comments),
            "status_counts": dict(sorted(Counter(item["status"] for item in review_index.values()).items())),
        },
        "issues": issues,
        "issue_counts": issue_counts,
        "audit_digest": _sha256(report_basis),
        "quality_gates": [
            "Base and block hashes are mechanically recomputed before any patch operation is applied.",
            "All operations validate before an in-memory all-or-none reduction; the base artifact is never modified.",
            "Unchanged blocks retain exact text, kind, ID, and digest across the revision lineage.",
            "Reviewer completion requires traceable manuscript locations and real evidence for claimed analyses, experiments, figures, and citations.",
            "Structural revisions require an explicit checkpoint and unresolved author input can never be labelled ready to submit.",
        ],
        "limitations": [
            "This structured reducer does not parse or redline DOCX or LaTeX files; an importer and exporter must preserve the same block and lineage contracts.",
            "Scientific sufficiency of supplied evidence remains subject to claim-evidence, statistical, ethical, and editorial review modules.",
        ],
    }
