"""Bounded activity presentation and once-per-completion library invalidation."""

from pathlib import Path

ACTIVE_STATUSES = {"queued", "running", "pausing", "cancelling"}
ATTENTION_STATUSES = {"failed", "paused"}


def activity_page(jobs, view="Active", limit=30):
    filters = {"Active": ACTIVE_STATUSES, "Needs attention": ATTENTION_STATUSES,
               "Completed": {"completed", "cancelled"}}
    allowed = filters.get(view)
    selected = [job for job in jobs if allowed is None or str(job.status) in allowed]
    selected.sort(key=lambda job: (str(job.status) not in ACTIVE_STATUSES, -job.created_at))
    return tuple(selected[:min(100, max(1, limit))]), len(selected)


def completed_roots(jobs, observed):
    """Observe a completed job exactly once, never rescan every one-second UI tick."""
    observed = set(observed)
    roots = set()
    for job in jobs:
        if str(job.status) == "completed" and job.files and job.id not in observed:
            observed.add(job.id)
            if getattr(job, "output_dir", None):
                roots.add(str(Path(job.output_dir).expanduser().resolve()))
    return observed, roots
