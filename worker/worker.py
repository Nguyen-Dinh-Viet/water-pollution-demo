from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, "/app")

from app.core.config import settings
from app.services.event_processor import process_event_payload
from app.services.persistence_service import claim_next_event, mark_event_done, mark_event_failed


POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", str(settings.worker_poll_seconds)))
WORKER_NAME = os.getenv("WORKER_NAME", settings.worker_name)


def main() -> None:
    print(f"[worker] starting name={WORKER_NAME} poll={POLL_SECONDS}s")
    while True:
        event = claim_next_event(WORKER_NAME)
        if not event:
            time.sleep(POLL_SECONDS)
            continue

        event_id = event["event_id"]
        try:
            payload = event["payload"]
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)
            result = process_event_payload(payload)
            mark_event_done(event_id, f"Processed by {WORKER_NAME}: {result['final_state']}")
            print(f"[worker] processed event={event_id} state={result['final_state']}")
        except Exception as exc:
            mark_event_failed(event_id, f"{type(exc).__name__}: {exc}")
            print(f"[worker] failed event={event_id}: {exc}")
            traceback.print_exc()
            time.sleep(min(POLL_SECONDS, 1.0))


if __name__ == "__main__":
    main()
