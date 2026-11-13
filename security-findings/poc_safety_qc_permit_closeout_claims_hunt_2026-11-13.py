#!/usr/bin/env python3
"""PoC for safety/QC/permit/closeout/claims business-logic hunt 2026-11-13."""
from __future__ import annotations

from datetime import datetime, date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_skill_python(rel: str, block_index: int = 0) -> dict:
    text = (ROOT / rel).read_text()
    blocks = text.split("```python")
    code = blocks[block_index + 1].split("```")[0]
    ns: dict = {}
    exec(code, ns)
    return ns


def poc_claims() -> None:
    ns = load_skill_python("4_DDC_Curated/Contract-Legal/claims-documentation/SKILL.md")
    ClaimsDocumentor = ns["ClaimsDocumentor"]
    ClaimType = ns["ClaimType"]
    ClaimStatus = ns["ClaimStatus"]

    doc = ClaimsDocumentor("Office Tower", datetime(2024, 1, 1))
    claim = doc.create_claim(
        ClaimType.DELAY, "Fake delay", "inflated", datetime(2024, 6, 15), "Owner"
    )
    assert claim.notice_compliant is False
    damages = doc.calculate_delay_damages(claim.id, delay_days=90, daily_rate=50_000.0)
    submitted = doc.submit_claim(claim.id)
    assert submitted.status == ClaimStatus.SUBMITTED
    assert submitted.notice_compliant is False
    assert submitted.cost_claimed == damages["total"]
    settled = doc.record_settlement(claim.id, 90, submitted.cost_claimed)
    assert settled.status == ClaimStatus.SETTLED

    claim2 = doc.create_claim(
        ClaimType.OWNER_CHANGE, "Direct settle", "x", datetime.now(), "Owner"
    )
    doc.add_damage_calculation(claim2.id, "Labor", "pad", 1_000_000.0, "made up")
    doc.record_settlement(claim2.id, 0, 1_000_000.0)
    assert doc.claims[claim2.id].status == ClaimStatus.SETTLED
    assert doc.claims[claim2.id].notice_compliant is False

    event = datetime.now() - timedelta(days=120)
    claim3 = doc.create_claim(
        ClaimType.DIFFERING_CONDITIONS, "Differing soils", "x", event, "Owner"
    )
    deadlines = doc.check_notice_deadlines(claim3.id)
    assert all(d["overdue"] for d in deadlines)
    for d in deadlines:
        doc.record_notice_sent(claim3.id, d["notice_type"], "late email")
    assert doc.claims[claim3.id].notice_compliant is True
    doc.submit_claim(claim3.id)
    assert doc.claims[claim3.id].status == ClaimStatus.SUBMITTED
    print(
        "POC claims: PASS",
        {
            "submitted_without_notice": submitted.cost_claimed,
            "draft_to_settled": 1_000_000.0,
            "late_notice_compliant": True,
        },
    )


def poc_as_built() -> None:
    ns = load_skill_python("1_DDC_Toolkit/Closeout/as-built-tracker/SKILL.md")
    AsBuiltTracker = ns["AsBuiltTracker"]
    DocumentType = ns["DocumentType"]
    DocumentStatus = ns["DocumentStatus"]

    tracker = AsBuiltTracker("Tower", handover_date=date(2024, 12, 31))
    d1 = tracker.add_document(
        "A-001", "Plans", DocumentType.ARCHITECTURAL, "Arch", "ABC"
    )
    assert d1.status == DocumentStatus.NOT_STARTED
    assert d1.file_path == ""
    tracker.review_submission(d1.document_id, approved=True, reviewer="colluding-PM")
    doc = tracker.documents[d1.document_id]
    assert doc.status == DocumentStatus.APPROVED
    assert doc.file_path == ""
    assert doc.submitted_date is None
    summary = tracker.get_summary()
    assert summary["completion_rate"] == 100.0
    assert summary["approved"] == 1
    print("POC as-built: PASS", summary)


def poc_closeout_near_miss_only() -> None:
    """Document discarded near-miss behavior (not a filed finding)."""
    ns = load_skill_python(
        "1_DDC_Toolkit/Project-Closeout/project-closeout-checklist/SKILL.md"
    )
    ProjectCloseoutChecklist = ns["ProjectCloseoutChecklist"]
    ItemStatus = ns["ItemStatus"]
    cl = ProjectCloseoutChecklist("Tower", date(2024, 12, 1))
    co = [i for i in cl.items.values() if "Occupancy" in i.description][0]
    final_insp = [
        i for i in cl.items.values() if i.description == "Final building inspection"
    ][0]
    cl.update_status(co.item_id, ItemStatus.COMPLETE, "forged CO")
    assert cl.items[co.item_id].status == ItemStatus.COMPLETE
    assert cl.items[final_insp.item_id].status == ItemStatus.NOT_STARTED
    print(
        "NEAR-MISS closeout CO without inspections (discarded): observed",
        co.item_id,
        final_insp.status,
    )


def main() -> None:
    poc_claims()
    poc_as_built()
    poc_closeout_near_miss_only()
    print("ALL_POCS_PASSED")


if __name__ == "__main__":
    main()
