"""Runs queued jobs (imports, push mirrors) one at a time. Its own container,
so a long import outlives web worker restarts."""

import logging
import signal
import time

from app import create_app

POLL_SECONDS = 2
log = logging.getLogger("mygit.worker")
stopping = False


def _stop(*_):
    global stopping
    stopping = True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    app = create_app()
    import jobs

    with app.app_context():
        jobs.recover_interrupted()
    log.info("worker ready")
    while not stopping:
        with app.app_context():
            job = jobs.claim()
            if job is None:
                time.sleep(POLL_SECONDS)
                continue
            log.info("job %s: %s for repo %s", job["id"], job["kind"], job["repo_id"])
            ok = jobs.run(job)
            log.info("job %s: %s", job["id"], "done" if ok else "failed")


if __name__ == "__main__":
    main()
