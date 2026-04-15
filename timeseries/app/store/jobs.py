from abc import ABC, abstractmethod
import time
import os
import json
import redis as redis_lib

_JOBS_DIR = "/tmp/skope_jobs"

class JobStore(ABC):
    @abstractmethod
    def update_job(self, job_id: str, status_data: dict) -> None:
        pass

    @abstractmethod
    def get_job_status(self, job_id: str) -> dict | None:
        pass


# Utility exposed to the app layer to clear old cache files
def cleanup_stale_jobs(max_age_hours: int = 24):
    if not os.path.exists(_JOBS_DIR):
        return
    now = time.time()
    for filename in os.listdir(_JOBS_DIR):
        filepath = os.path.join(_JOBS_DIR, filename)
        if os.path.isfile(filepath):
            if os.stat(filepath).st_mtime < now - (max_age_hours * 3600):
                os.remove(filepath)

# File system implementation for simplicity
# Could be replaced with Redis or SQLite 
class FileSystemJobStore(JobStore):
    def __init__(self, directory: str = _JOBS_DIR):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def update_job(self, job_id: str, status_data: dict) -> None:
        file_path = os.path.join(self.directory, f"{job_id}.json")
        temp_path = f"{file_path}.tmp"
        with open(temp_path, "w") as f:
            json.dump(status_data, f)
        os.rename(temp_path, file_path)

    def get_job_status(self, job_id: str) -> dict | None:
        file_path = os.path.join(self.directory, f"{job_id}.json")
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r") as f:
            return json.load(f)

_JOB_TTL_SECONDS = 86400  # 24 hours — matches cleanup_stale_jobs default


class RedisJobStore(JobStore):
    def __init__(self, redis_url: str):
        self._client = redis_lib.Redis.from_url(redis_url, decode_responses=True)

    def update_job(self, job_id: str, status_data: dict) -> None:
        self._client.set(f"job:{job_id}", json.dumps(status_data), ex=_JOB_TTL_SECONDS)

    def get_job_status(self, job_id: str) -> dict | None:
        raw = self._client.get(f"job:{job_id}")
        if raw is None:
            return None
        return json.loads(raw)


def get_job_store() -> JobStore:
    from app.config import get_settings
    settings = get_settings()
    if settings.redis_url:
        return RedisJobStore(settings.redis_url)
    return FileSystemJobStore()