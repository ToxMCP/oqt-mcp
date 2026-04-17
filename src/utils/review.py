"""Lightweight in-memory review checkpoint orchestrator (OQT-02)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

log = logging.getLogger(__name__)


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ReviewCheckpoint:
    """A single review checkpoint within a workflow."""

    def __init__(
        self,
        workflow_id: str,
        step: str,
        data: Dict[str, Any],
        expires_minutes: int = 60,
    ):
        self.checkpoint_id = f"{workflow_id}_{step}_{uuid4().hex[:8]}"
        self.workflow_id = workflow_id
        self.step = step
        self.status = ReviewDecision.PENDING
        self.data = data
        self.reviewer_id: Optional[str] = None
        self.reviewed_at: Optional[str] = None
        self.comments: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        ).isoformat()

    def is_expired(self) -> bool:
        try:
            expiry = datetime.fromisoformat(self.expires_at)
        except (TypeError, ValueError):
            return False
        return datetime.now(timezone.utc) > expiry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_id": self.workflow_id,
            "step": self.step,
            "status": self.status.value,
            "data": self.data,
            "reviewer_id": self.reviewer_id,
            "reviewed_at": self.reviewed_at,
            "comments": self.comments,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class ReviewOrchestrator:
    """In-memory orchestrator for workflow review checkpoints."""

    def __init__(self):
        self._checkpoints: Dict[str, ReviewCheckpoint] = {}
        self._workflow_index: Dict[str, List[str]] = {}

    def create_checkpoint(
        self,
        workflow_id: str,
        step: str,
        data: Dict[str, Any],
        expires_minutes: int = 60,
    ) -> ReviewCheckpoint:
        checkpoint = ReviewCheckpoint(workflow_id, step, data, expires_minutes)
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        self._workflow_index.setdefault(workflow_id, []).append(checkpoint.checkpoint_id)
        log.info("Created review checkpoint %s for workflow %s", checkpoint.checkpoint_id, workflow_id)
        return checkpoint

    def _raw_workflow_checkpoints(self, workflow_id: str) -> List[ReviewCheckpoint]:
        """Return checkpoints without triggering expiry enforcement."""
        ids = self._workflow_index.get(workflow_id, [])
        return [self._checkpoints[cid] for cid in ids if cid in self._checkpoints]

    def _enforce_expiry(self, workflow_id: str) -> None:
        """Mark pending checkpoints as EXPIRED if their deadline has passed."""
        for cp in self._raw_workflow_checkpoints(workflow_id):
            if cp.status == ReviewDecision.PENDING and cp.is_expired():
                cp.status = ReviewDecision.EXPIRED
                cp.comments = "Checkpoint expired before review."
                cp.reviewed_at = datetime.now(timezone.utc).isoformat()
                log.warning("Checkpoint %s expired and was auto-rejected.", cp.checkpoint_id)

    def get_checkpoint(self, checkpoint_id: str) -> Optional[ReviewCheckpoint]:
        cp = self._checkpoints.get(checkpoint_id)
        if cp and cp.status == ReviewDecision.PENDING and cp.is_expired():
            self._enforce_expiry(cp.workflow_id)
        return self._checkpoints.get(checkpoint_id)

    def get_workflow_checkpoints(self, workflow_id: str) -> List[ReviewCheckpoint]:
        self._enforce_expiry(workflow_id)
        return self._raw_workflow_checkpoints(workflow_id)

    def submit_review(
        self,
        checkpoint_id: str,
        reviewer_id: str,
        decision: ReviewDecision,
        comments: Optional[str] = None,
    ) -> ReviewCheckpoint:
        checkpoint = self._checkpoints.get(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Unknown checkpoint: {checkpoint_id}")
        if checkpoint.status == ReviewDecision.PENDING and checkpoint.is_expired():
            self._enforce_expiry(checkpoint.workflow_id)
            raise ValueError(f"Checkpoint expired before review: {checkpoint_id}")
        if checkpoint.status != ReviewDecision.PENDING:
            raise ValueError(f"Checkpoint already reviewed: {checkpoint.status.value}")
        checkpoint.status = decision
        checkpoint.reviewer_id = reviewer_id
        checkpoint.reviewed_at = datetime.now(timezone.utc).isoformat()
        checkpoint.comments = comments
        log.info(
            "Review submitted for checkpoint %s: %s by %s",
            checkpoint_id,
            decision.value,
            reviewer_id,
        )
        return checkpoint

    def all_approved(self, workflow_id: str) -> bool:
        self._enforce_expiry(workflow_id)
        checkpoints = self.get_workflow_checkpoints(workflow_id)
        if not checkpoints:
            return True
        return all(c.status == ReviewDecision.APPROVED for c in checkpoints)

    def any_rejected(self, workflow_id: str) -> bool:
        self._enforce_expiry(workflow_id)
        checkpoints = self.get_workflow_checkpoints(workflow_id)
        return any(c.status == ReviewDecision.REJECTED for c in checkpoints)

    def pending_checkpoints(self, workflow_id: str) -> List[ReviewCheckpoint]:
        self._enforce_expiry(workflow_id)
        return [c for c in self.get_workflow_checkpoints(workflow_id) if c.status == ReviewDecision.PENDING]

    def get_checkpoint_by_step(self, workflow_id: str, step: str) -> Optional[ReviewCheckpoint]:
        for cp in self.get_workflow_checkpoints(workflow_id):
            if cp.step == step:
                return cp
        return None

    def create_checkpoint_if_missing(
        self,
        workflow_id: str,
        step: str,
        data: Dict[str, Any],
        expires_minutes: int = 60,
    ) -> ReviewCheckpoint:
        existing = self.get_checkpoint_by_step(workflow_id, step)
        if existing:
            return existing
        return self.create_checkpoint(workflow_id, step, data, expires_minutes)


# Global orchestrator instance
review_orchestrator = ReviewOrchestrator()
