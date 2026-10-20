"""Unit tests for SingleInstanceLock."""

import os
import tempfile
import pytest

from handsfree.os_layer.lock import SingleInstanceLock


def test_acquire_and_release_lock():
    fd, path = tempfile.mkstemp(suffix=".lock")
    os.close(fd)
    os.remove(path)

    lock1 = SingleInstanceLock(lock_path=path)
    assert lock1.acquire() is True
    assert os.path.exists(path)

    # Releasing should remove or unlock the file
    lock1.release()
    assert lock1.fd is None


def test_second_instance_takeover():
    fd, path = tempfile.mkstemp(suffix=".lock")
    os.close(fd)
    os.remove(path)

    lock1 = SingleInstanceLock(lock_path=path)
    assert lock1.acquire() is True

    # Attempting to acquire without takeover should fail
    lock2 = SingleInstanceLock(lock_path=path)
    # Since lock1 is in current process, takeover terminates existing pid if different,
    # or fails if same pid.
    assert lock2.acquire(takeover=False) is False

    lock1.release()
    lock2.release()
