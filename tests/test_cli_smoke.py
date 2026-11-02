"""CLI entry points import and parse arguments without touching the network."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, "-I", *args], capture_output=True, text=True, cwd=ROOT, timeout=60)


def test_agmarknet_collect_help_lists_subcommands():
    r = run("collectors/agmarknet_collect.py", "--help")
    assert r.returncode == 0
    for cmd in ("masters", "state-monthly", "market-sample", "price-trend"):
        assert cmd in r.stdout


def test_agmarknet_collect_requires_a_subcommand():
    assert run("collectors/agmarknet_collect.py").returncode == 2


def test_upag_collect_unknown_job_runs_nothing():
    r = run("collectors/upag_collect.py", "no-such-job")
    assert r.returncode == 0 and r.stdout == ""
