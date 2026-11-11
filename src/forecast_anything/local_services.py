"""Own the local API socket and supervise the API and worker subprocesses."""

import errno
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import uuid4

from .contracts import DomainError
from .store import Ledger


@contextmanager
def local_lock(path: Path, busy_code: str):
    """A stable inode allows the OS to release ownership even on process death."""
    try:
        import fcntl
    except ImportError:
        raise DomainError("local_process_lock_unsupported", {}) from None
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "rb") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DomainError(busy_code, {}) from None
        yield


def worker_lock(db: Path):
    path = db.resolve()
    if path.exists() and path.stat().st_nlink != 1:
        raise DomainError("ledger_hardlink_unsupported", {})
    return local_lock(
        path.with_name(path.name + ".worker.lock"), "worker_already_running"
    )


def reserve_port(host: str, port: int) -> socket.socket:
    if not 0 <= port <= 65535:
        raise DomainError(
            "invalid_port", {"recovery": "Choose a port between 1 and 65535."}
        )
    listener = socket.socket()
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen()
    except OSError as error:
        listener.close()
        if error.errno == errno.EADDRINUSE:
            raise DomainError(
                "port_in_use",
                {
                    "port": port,
                    "recovery": "Stop the process using this port or choose a different port for a new workspace.",
                },
            ) from None
        raise
    return listener


def run_services(db: Path, host: str, port: int, *, verify_model: bool = False) -> int:
    if os.name != "posix":
        raise DomainError("local_supervisor_unsupported", {})
    children = []
    stopped = False

    def stop_on_signal(signum, frame):
        nonlocal stopped
        stopped = True

    previous = {
        signum: signal.signal(signum, stop_on_signal)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        base = [sys.executable, "-m", "forecast_anything.cli"]
        env = {
            **os.environ,
            "FORECAST_ANYTHING_SUPERVISOR_ID": uuid4().hex,
            "FORECAST_ANYTHING_SUPERVISOR_PID": str(os.getpid()),
        }
        with reserve_port(host, port) as listener:
            with worker_lock(db):
                Ledger(db)
            if stopped:
                return 0
            fd = listener.fileno()
            api = subprocess.Popen(
                [*base, "serve", "--db", str(db), "--socket-fd", str(fd)],
                pass_fds=(fd,),
                env=env,
            )
            children.append(api)
        worker = [*base, "worker", "--db", str(db)]
        if verify_model:
            worker.append("--verify-model")
        if stopped:
            return 0
        worker_process = subprocess.Popen(worker, env=env)
        children.append(worker_process)
        while not stopped:
            api_code = api.poll()
            if api_code is not None:
                print(
                    f"API stopped (exit {api_code}); stopping services.",
                    file=sys.stderr,
                )
                return 1
            worker_code = worker_process.poll()
            if worker_code is not None:
                if worker_code != 124:
                    print(
                        f"worker stopped (exit {worker_code}); stopping services.",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    "worker reached its execution deadline; restarting worker.",
                    file=sys.stderr,
                )
                time.sleep(1)
                if stopped:
                    break
                worker_process = subprocess.Popen(worker, env=env)
                children.append(worker_process)
            time.sleep(0.2)
        return 0
    except OSError as error:
        print(f"Could not start local services: {error}", file=sys.stderr)
        return 1
    finally:
        # Signals request a stop without interrupting child creation or teardown.
        try:
            for child in children:
                if child.poll() is None:
                    with suppress(ProcessLookupError):
                        child.terminate()
            for child in children:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
