"""Job tracker for async ingestion progress."""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class IngestJob:
    job_id: str
    collection: str
    filename: str
    strategy: str
    sensitivity: str
    status: str = "chunking"  # chunking → uploading → done → failed
    total_chunks: int = 0
    uploaded_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def progress_pct(self) -> int:
        if self.total_chunks == 0:
            return 0
        return int(self.uploaded_chunks * 100 / self.total_chunks)

    def to_dict(self) -> dict:
        elapsed = time.time() - self.created_at
        return {
            "job_id": self.job_id,
            "collection": self.collection,
            "filename": self.filename,
            "strategy": self.strategy,
            "sensitivity": self.sensitivity,
            "status": self.status,
            "total_chunks": self.total_chunks,
            "uploaded_chunks": self.uploaded_chunks,
            "completed_chunks": self.completed_chunks,
            "failed_chunks": self.failed_chunks,
            "progress_pct": self.progress_pct,
            "elapsed_seconds": round(elapsed, 1),
            "error": self.error,
        }


# In-memory store (sufficient for single-instance beta)
_jobs: dict[str, IngestJob] = {}


def create_job(collection: str, filename: str, strategy: str, sensitivity: str) -> IngestJob:
    job = IngestJob(
        job_id=str(uuid.uuid4())[:8],
        collection=collection,
        filename=filename,
        strategy=strategy,
        sensitivity=sensitivity,
    )
    _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> IngestJob | None:
    return _jobs.get(job_id)


def list_jobs(collection: str | None = None) -> list[dict]:
    jobs = _jobs.values()
    if collection:
        jobs = [j for j in jobs if j.collection == collection]
    return [j.to_dict() for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)]
