"""Thread-based daemon runner for the menu bar app.

Runs CaptureDaemon in a background thread instead of a subprocess,
which is more reliable inside a .app bundle.
"""
import logging
import threading
from typing import Callable, Optional

from .daemon import CaptureDaemon

logger = logging.getLogger(__name__)


class DaemonThread:
    """Manages a CaptureDaemon running in a background thread."""

    def __init__(self, on_error: Optional[Callable[[Exception], None]] = None):
        """Initialize the daemon thread wrapper.

        Args:
            on_error: Optional callback invoked on the daemon thread when
                      the daemon crashes with an unhandled exception.
        """
        self._thread: Optional[threading.Thread] = None
        self._daemon: Optional[CaptureDaemon] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._on_error = on_error
        self._last_error: Optional[Exception] = None

    # -- public API --

    def start(self) -> None:
        """Start the capture daemon in a background thread.

        Raises RuntimeError if already running.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Daemon thread is already running")

            self._last_error = None
            self._stop_event.clear()
            self._daemon = CaptureDaemon(
                in_process=True, stop_event=self._stop_event,
            )
            self._thread = threading.Thread(
                target=self._run,
                name="coachy-daemon",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Signal the daemon to stop and wait for the thread to finish.

        Args:
            timeout: Maximum seconds to wait for the thread to exit.
        """
        # Signal stop via event (interrupts sleep immediately)
        self._stop_event.set()
        with self._lock:
            if self._daemon is not None:
                self._daemon.running = False

        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        """Return True if the daemon thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> Optional[Exception]:
        """The last unhandled exception from the daemon thread, if any."""
        return self._last_error

    # -- internals --

    def _run(self) -> None:
        """Thread target: run the daemon, catching crashes."""
        try:
            self._daemon.run()
        except Exception as exc:
            self._last_error = exc
            logger.error(f"Daemon thread crashed: {exc}", exc_info=True)
            if self._on_error is not None:
                try:
                    self._on_error(exc)
                except Exception:
                    pass  # don't let callback errors propagate
