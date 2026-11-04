"""Run the local API and worker together in the foreground."""

import signal
import subprocess
import sys
import time
from pathlib import Path


def run_services(db: Path, host: str, port: int) -> int:
    children = []
    previous = signal.getsignal(signal.SIGTERM)

    def stop_on_signal(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_on_signal)
    try:
        base = [sys.executable, "-m", "forecast_anything.cli"]
        children.append(
            subprocess.Popen(
                [*base, "serve", "--db", str(db), "--host", host, "--port", str(port)]
            )
        )
        children.append(subprocess.Popen([*base, "worker", "--db", str(db)]))
        while True:
            for name, child in zip(("API", "worker"), children, strict=True):
                code = child.poll()
                if code is not None:
                    print(
                        f"{name} stopped (exit {code}); stopping services.",
                        file=sys.stderr,
                    )
                    return 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    except OSError as error:
        print(f"Could not start local services: {error}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)
        for child in children:
            if child.poll() is None:
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
