import pytest

from src.utils.review import ReviewDecision, ReviewOrchestrator


@pytest.fixture
def orchestrator():
    return ReviewOrchestrator()


def test_create_checkpoint(orchestrator):
    cp = orchestrator.create_checkpoint("wf-1", "chemical_identity", {"chem_id": "123"})
    assert cp.workflow_id == "wf-1"
    assert cp.step == "chemical_identity"
    assert cp.status == ReviewDecision.PENDING


def test_get_checkpoint_by_step(orchestrator):
    orchestrator.create_checkpoint("wf-1", "chemical_identity", {"chem_id": "123"})
    found = orchestrator.get_checkpoint_by_step("wf-1", "chemical_identity")
    assert found is not None
    assert found.step == "chemical_identity"


def test_create_checkpoint_if_missing_does_not_duplicate(orchestrator):
    cp1 = orchestrator.create_checkpoint_if_missing(
        "wf-1", "chemical_identity", {"chem_id": "123"}
    )
    cp2 = orchestrator.create_checkpoint_if_missing(
        "wf-1", "chemical_identity", {"chem_id": "456"}
    )
    assert cp1.checkpoint_id == cp2.checkpoint_id


def test_submit_review_approves(orchestrator):
    cp = orchestrator.create_checkpoint("wf-1", "chemical_identity", {})
    updated = orchestrator.submit_review(
        cp.checkpoint_id, "user-1", ReviewDecision.APPROVED, "Looks good"
    )
    assert updated.status == ReviewDecision.APPROVED
    assert updated.reviewer_id == "user-1"
    assert updated.comments == "Looks good"


def test_submit_review_rejects(orchestrator):
    cp = orchestrator.create_checkpoint("wf-1", "ad_assessment", {})
    updated = orchestrator.submit_review(
        cp.checkpoint_id, "user-1", ReviewDecision.REJECTED
    )
    assert updated.status == ReviewDecision.REJECTED


def test_all_approved_true_when_approved(orchestrator):
    cp = orchestrator.create_checkpoint("wf-1", "chemical_identity", {})
    orchestrator.submit_review(cp.checkpoint_id, "user-1", ReviewDecision.APPROVED)
    assert orchestrator.all_approved("wf-1") is True


def test_any_rejected_true_when_rejected(orchestrator):
    cp = orchestrator.create_checkpoint("wf-1", "chemical_identity", {})
    orchestrator.submit_review(cp.checkpoint_id, "user-1", ReviewDecision.REJECTED)
    assert orchestrator.any_rejected("wf-1") is True


def test_pending_checkpoints_filters_correctly(orchestrator):
    cp1 = orchestrator.create_checkpoint("wf-1", "chemical_identity", {})
    cp2 = orchestrator.create_checkpoint("wf-1", "ad_assessment", {})
    orchestrator.submit_review(cp1.checkpoint_id, "user-1", ReviewDecision.APPROVED)
    pending = orchestrator.pending_checkpoints("wf-1")
    assert len(pending) == 1
    assert pending[0].checkpoint_id == cp2.checkpoint_id


def test_submit_review_unknown_checkpoint_raises(orchestrator):
    with pytest.raises(ValueError, match="Unknown checkpoint"):
        orchestrator.submit_review("bad-id", "user-1", ReviewDecision.APPROVED)


def test_submit_review_already_reviewed_raises(orchestrator):
    cp = orchestrator.create_checkpoint("wf-1", "chemical_identity", {})
    orchestrator.submit_review(cp.checkpoint_id, "user-1", ReviewDecision.APPROVED)
    with pytest.raises(ValueError, match="already reviewed"):
        orchestrator.submit_review(cp.checkpoint_id, "user-1", ReviewDecision.REJECTED)


def test_expired_checkpoint_auto_rejected(orchestrator):
    cp = orchestrator.create_checkpoint(
        "wf-1", "chemical_identity", {}, expires_minutes=-1
    )
    # Lazy expiry enforcement on access
    assert cp.is_expired() is True
    pending = orchestrator.pending_checkpoints("wf-1")
    assert len(pending) == 0
    fetched = orchestrator.get_checkpoint(cp.checkpoint_id)
    assert fetched is not None
    assert fetched.status == ReviewDecision.EXPIRED


def test_submit_review_after_expiry_raises(orchestrator):
    cp = orchestrator.create_checkpoint(
        "wf-1", "chemical_identity", {}, expires_minutes=-1
    )
    with pytest.raises(ValueError, match="expired"):
        orchestrator.submit_review(cp.checkpoint_id, "user-1", ReviewDecision.APPROVED)


def test_all_approved_after_expiry_is_false(orchestrator):
    cp = orchestrator.create_checkpoint(
        "wf-1", "chemical_identity", {}, expires_minutes=-1
    )
    assert orchestrator.all_approved("wf-1") is False


def test_any_rejected_after_expiry_is_false(orchestrator):
    # EXPIRED is not REJECTED, so any_rejected should be False for EXPIRED
    orchestrator.create_checkpoint("wf-1", "chemical_identity", {}, expires_minutes=-1)
    orchestrator.any_rejected("wf-1")  # trigger expiry enforcement
    assert orchestrator.any_rejected("wf-1") is False
