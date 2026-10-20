"""Single instance lock to ensure only one HandsFreeOS daemon runs at any time."""

import atexit
import fcntl
import logging
import os
import signal
import subprocess
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

LOCK_FILE = "/tmp/handsfree.lock"


class SingleInstanceLock:
    """Guarantees only one HandsFreeOS process runs on the host."""

    def __init__(self, lock_path: str = LOCK_FILE):
        self.lock_path = lock_path
        self.fd: Optional[int] = None

    def acquire(self, takeover: bool = True) -> bool:
        """Acquires lock. If another instance exists and takeover=True, terminates it."""
        try:
            self.fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        except Exception as e:
            logger.warning(f"Failed to open lock file {self.lock_path}: {e}")
            return True

        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            # Another process holds the lock
            if not takeover:
                return False

            existing_pid = self._find_target_pid()
            if existing_pid and existing_pid != os.getpid():
                logger.warning(
                    f"Another HandsFreeOS instance (PID {existing_pid}) is already running. "
                    "Terminating previous instance to ensure strictly 1 single instance..."
                )
                self._terminate_pid(existing_pid)

            # Wait briefly and retry acquiring lock
            acquired = False
            for _ in range(15):
                time.sleep(0.1)
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except (BlockingIOError, OSError):
                    continue

            if not acquired:
                logger.error("Could not acquire lock after terminating previous instance")
                return False

        # Write our PID
        try:
            os.ftruncate(self.fd, 0)
            os.lseek(self.fd, 0, os.SEEK_SET)
            os.write(self.fd, f"{os.getpid()}\n".encode("utf-8"))
            os.fsync(self.fd)
        except Exception:
            pass

        atexit.register(self.release)
        return True

    def _find_target_pid(self) -> Optional[int]:
        # Try reading from lock file first with brief retries
        for _ in range(5):
            pid = self._read_existing_pid()
            if pid:
                return pid
            time.sleep(0.05)

        # Fallback: scan for any other handsfree process via pgrep
        pids = self._find_handsfree_pids()
        if pids:
            return pids[0]
        return None

    def _read_existing_pid(self) -> Optional[int]:
        try:
            os.lseek(self.fd, 0, os.SEEK_SET)
            content = os.read(self.fd, 32).decode("utf-8").strip()
            return int(content) if content.isdigit() else None
        except Exception:
            return None

    def _find_handsfree_pids(self) -> List[int]:
        try:
            res = subprocess.run(["pgrep", "-f", "handsfree"], capture_output=True, text=True, check=False)
            my_pid = os.getpid()
            pids = []
            for line in res.stdout.strip().splitlines():
                line = line.strip()
                if line.isdigit():
                    p = int(line)
                    if p != my_pid:
                        pids.append(p)
            return pids
        except Exception:
            return []

    def _terminate_pid(self, pid: int) -> None:
        if pid == os.getpid():
            return
        try:
            # Terminate process group if available
            try:
                pgid = os.getpgid(pid)
                if pgid != os.getpgrp():
                    os.killpg(pgid, signal.SIGTERM)
            except Exception:
                pass

            os.kill(pid, signal.SIGTERM)
            for _ in range(15):
                time.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except OSError:
                    # Successfully stopped
                    return

            # Force kill if process ignores SIGTERM
            try:
                pgid = os.getpgid(pid)
                if pgid != os.getpgrp():
                    os.killpg(pgid, signal.SIGKILL)
            except Exception:
                pass
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def release(self) -> None:
        """Releases the instance lock and cleans up."""
        if self.fd is not None:
            try:
                try:
                    os.ftruncate(self.fd, 0)
                except Exception:
                    pass
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None
