"""Promotion: fully verify the pinned releases before a deploy (release spec TXN-011).

    python -m app.registry.verify

Runs every startup check (PIN-004) and also compares every file's checksum
with its manifest. Prints one JSON line per verified release and exits 0, or
logs each failed check and exits 1.
"""

import json
import sys
from pathlib import Path

from app.config import get_settings
from app.registry.compose import ReleaseRefused, load_pin, log_refusals, verify_releases


def main() -> int:
    settings = get_settings()
    pin = load_pin(Path(settings.release_pin_path))
    try:
        registry = verify_releases(pin, Path(settings.release_root), full=True)
    except ReleaseRefused as exc:
        log_refusals(exc.refusals)
        print(f"verification failed: {len(exc.refusals)} check(s); see the log")
        return 1
    for pinned in pin.releases:
        release = registry.get(pinned.dataset)
        print(
            json.dumps(
                {
                    "dataset": pinned.dataset,
                    "release_id": pinned.release_id,
                    "declaration_digest": pinned.declaration_digest,
                    "manifest_sha256": pinned.manifest_sha256,
                    "path": str(release.path),
                    "verification": "full",
                    "result": "passed",
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
