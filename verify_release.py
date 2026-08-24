"""Release verification for DrillMaster (no GUI required)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def run(command):
    print("$", " ".join(command))
    return subprocess.run(command, cwd=ROOT, check=False).returncode

def main():
    if run([sys.executable, "-m", "compileall", "-q", "."]):
        return 1
    if run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]):
        return 1
    print("Release verification passed: syntax + core regression tests")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
