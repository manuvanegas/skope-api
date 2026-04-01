import json
import os
import time

import pytest

from app.store.jobs import cleanup_stale_jobs


# ---------------------------------------------------------------------------
# FileSystemJobStore

def test_update_job_creates_file(fs_job_store, tmp_jobs_dir):
    fs_job_store.update_job("job-001", {"status": "pending"})
    file_path = os.path.join(tmp_jobs_dir, "job-001.json")
    assert os.path.exists(file_path)
    with open(file_path) as f:
        assert json.load(f) == {"status": "pending"}


def test_update_job_atomic_overwrite(fs_job_store, tmp_jobs_dir):
    fs_job_store.update_job("job-002", {"status": "pending"})
    fs_job_store.update_job("job-002", {"status": "complete"})
    file_path = os.path.join(tmp_jobs_dir, "job-002.json")
    with open(file_path) as f:
        assert json.load(f) == {"status": "complete"}
    # No leftover .tmp file
    assert not os.path.exists(file_path + ".tmp")


def test_get_job_status_existing(fs_job_store):
    fs_job_store.update_job("job-003", {"status": "processing", "progress": 50})
    result = fs_job_store.get_job_status("job-003")
    assert result == {"status": "processing", "progress": 50}


def test_get_job_status_missing_returns_none(fs_job_store):
    result = fs_job_store.get_job_status("nonexistent-id")
    assert result is None


# ---------------------------------------------------------------------------
# cleanup_stale_jobs

def test_cleanup_removes_old_files(tmp_path, monkeypatch):
    monkeypatch.setattr("app.store.jobs._JOBS_DIR", str(tmp_path))
    # Create a file and backdate it to 25 hours ago
    old_file = tmp_path / "old-job.json"
    old_file.write_text('{"status": "done"}')
    old_time = time.time() - (25 * 3600)
    os.utime(str(old_file), (old_time, old_time))
    # Create a recent file
    recent_file = tmp_path / "recent-job.json"
    recent_file.write_text('{"status": "pending"}')

    cleanup_stale_jobs(max_age_hours=24)

    assert not old_file.exists()
    assert recent_file.exists()


def test_cleanup_missing_dir_no_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.store.jobs._JOBS_DIR", str(tmp_path / "nonexistent"))
    cleanup_stale_jobs(max_age_hours=24)  # should return silently


def test_cleanup_keeps_recent_files(tmp_path, monkeypatch):
    monkeypatch.setattr("app.store.jobs._JOBS_DIR", str(tmp_path))
    recent_file = tmp_path / "fresh-job.json"
    recent_file.write_text('{"status": "pending"}')

    cleanup_stale_jobs(max_age_hours=24)

    assert recent_file.exists()
