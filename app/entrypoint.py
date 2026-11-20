import os
import subprocess
import sys
import time


def main() -> None:
    for attempt in range(1, 16):
        completed = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False)
        if completed.returncode == 0:
            break
        print(f"Aguardando o banco ({attempt}/15)...", flush=True)
        time.sleep(2)
    else:
        raise SystemExit(1)
    os.execv(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
