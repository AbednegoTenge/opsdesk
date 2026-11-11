"""Exit 0 if a heartbeat file is fresh, 1 otherwise.

    python -m opsdesk_tasks.healthcheck worker        # checks WORKER_HEARTBEAT_FILE
    python -m opsdesk_tasks.healthcheck beat          # checks BEAT_HEARTBEAT_FILE
    python -m opsdesk_tasks.healthcheck worker --max-age 60

Reads only environment variables, not Django settings, so the probe is cheap.
"""

import argparse
import os
import sys
import time

DEFAULTS = {
    "worker": ("WORKER_HEARTBEAT_FILE", "/tmp/opsdesk-worker-heartbeat"),  # noqa: S108
    "beat": ("BEAT_HEARTBEAT_FILE", "/tmp/opsdesk-beat-heartbeat"),  # noqa: S108
}


def check(path: str, max_age: float, now: float | None = None) -> tuple[bool, str]:
    try:
        age = (now or time.time()) - os.path.getmtime(path)
    except OSError:
        return False, f"no heartbeat file at {path}"
    if age > max_age:
        return False, f"heartbeat is {age:.0f}s old (max {max_age:.0f}s)"
    return True, f"heartbeat {age:.0f}s old"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("process", choices=list(DEFAULTS))
    parser.add_argument("--max-age", type=float, default=60.0)
    args = parser.parse_args(argv)
    env_var, default = DEFAULTS[args.process]
    ok, message = check(os.environ.get(env_var, default), args.max_age)
    print(("OK: " if ok else "UNHEALTHY: ") + message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
