"""Run with the Anvil application stopped; retained infrastructure stays running."""

import socket
import subprocess

from anvil.config import ROOT

assert not (ROOT / ".local/processes.json").exists(), "Stop registered Anvil app processes first"
with socket.socket() as occupied:
    occupied.bind(("127.0.0.1", 3202))
    occupied.listen(1)
    result = subprocess.run(
        ["python3", "scripts/local.py", "dev"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode != 0 and "Port 3202 is occupied" in result.stderr
    assert not (ROOT / ".local/processes.json").exists()
    assert occupied.getsockname()[1] == 3202
print("Occupied-port preflight refused startup without touching the existing listener.")
