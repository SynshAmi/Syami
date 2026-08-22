import logging
import threading

from syami.application.documents.worker import DocumentProcessingWorker


logger = logging.getLogger(__name__)


class DocumentProcessingScheduler:

    def __init__(
        self,
        worker: DocumentProcessingWorker | None = None,
        interval_seconds: float = 1800.0,
        batch_size: int = 10,
    ):
        self._worker = worker or DocumentProcessingWorker()
        self._interval_seconds = interval_seconds
        self._batch_size = batch_size
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="SyamiDocumentProcessingScheduler",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                return

            self._stop_event.set()
            thread = self._thread

        thread.join(timeout=timeout)

        with self._lock:
            self._thread = None

    def trigger_now(self) -> dict[str, int]:
        try:
            return self._worker.run(batch_size=self._batch_size)
        except Exception as error:
            logger.exception(
                "Unexpected error during manual scheduler trigger: %s",
                error,
            )
            return {
                "claimed": 0,
                "completed": 0,
                "unsupported": 0,
                "failed": 0,
            }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._worker.run(batch_size=self._batch_size)
            except Exception as error:
                logger.exception(
                    "Unexpected error in document processing scheduler: %s",
                    error,
                )

            if self._stop_event.wait(timeout=self._interval_seconds):
                break
