import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_toolbox_help_exits_cleanly():
    repo = _repo_root()
    proc = subprocess.run(
        [sys.executable, "toolbox.py", "--help"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "Tools Suite" in (proc.stdout + proc.stderr)


# The `test_toolbox_doctor_exits_cleanly` function is a unit test written in Python. It is testing the
# behavior of a command-line tool called `toolbox.py` with the argument "doctor".
def test_toolbox_doctor_exits_cleanly():
    repo = _repo_root()
    proc = subprocess.run(
        [sys.executable, "toolbox.py", "doctor"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "TOOLS SUITE DOCTOR" in (proc.stdout + proc.stderr)
