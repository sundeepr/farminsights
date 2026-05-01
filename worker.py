import asyncio
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime

import session_state

logger = logging.getLogger(__name__)

batch_queue: queue.Queue = queue.Queue()

_UPLOADS_BASE = 'data/uploads'


async def process_batch(session_id: str, batch_index: int, image_paths: list[str]) -> dict:
    """Stub — replace this body with a call to the real processing script.

    Contract:
      Input:  session_id (str)
              batch_index (int)
              image_paths (list[str]) — absolute paths to image files
      Output: dict matching the plant health report schema
    """
    raise NotImplementedError(
        "Wire in the real processing script: replace this function body in worker.py"
    )


def _save_report(session_id: str, batch_index: int, report: dict) -> str:
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'report_batch_{batch_index}_{timestamp}.json'
    path = os.path.join(_UPLOADS_BASE, session_id, filename)
    with open(path, 'w') as f:
        json.dump(report, f, indent=2)
    return filename


def worker_loop():
    while True:
        job = batch_queue.get()
        session_id, batch_index, image_paths = job
        try:
            logger.info('Processing batch %d for session %s (%d images)',
                        batch_index, session_id, len(image_paths))
            report = asyncio.run(process_batch(session_id, batch_index, image_paths))
            report_filename = _save_report(session_id, batch_index, report)
            session_state.mark_batch_complete(session_id, batch_index, report_filename)
            logger.info('Batch %d for session %s complete → %s',
                        batch_index, session_id, report_filename)
        except NotImplementedError:
            logger.warning('process_batch is a stub — wire in the real script in worker.py')
            session_state.mark_batch_failed(session_id, batch_index,
                                            'processing script not yet wired')
        except Exception as e:
            logger.error('Batch %d for session %s failed: %s', batch_index, session_id, e)
            session_state.mark_batch_failed(session_id, batch_index, str(e))
        finally:
            batch_queue.task_done()


def flush_pending(interval_minutes: int):
    while True:
        time.sleep(interval_minutes * 60)
        for sid in session_state.sessions_with_pending():
            result = session_state.flush_session(sid)
            if result:
                batch_index, image_paths = result
                batch_queue.put((sid, batch_index, image_paths))
                logger.info('Flush: queued %d image(s) for session %s as batch %d',
                            len(image_paths), sid, batch_index)


def start_worker(flush_interval_minutes: int = 5):
    threading.Thread(target=worker_loop, daemon=True, name='batch-worker').start()
    threading.Thread(target=flush_pending, args=(flush_interval_minutes,),
                     daemon=True, name='flush-timer').start()
    logger.info('Worker started (flush interval: %d min)', flush_interval_minutes)
