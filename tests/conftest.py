"""Shared helpers: run a repo script against a synthetic project root, fully offline."""
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def run_script(rel, fake_root, argv=(), name="__main__"):
    """Execute REPO/rel as a script whose ``Path(__file__).resolve()`` lands inside ``fake_root``.

    ``__file__`` stays the real path (so coverage attributes the lines to the real file); only
    ``Path.resolve`` is redirected for that one path, which makes ``ROOT = ...resolve().parents[n]``
    point at the synthetic tree.
    """
    real = REPO / rel
    fake = pathlib.Path(fake_root) / rel
    fake.parent.mkdir(parents=True, exist_ok=True)
    code = compile(real.read_text(encoding="utf-8"), str(real), "exec")
    g = {"__file__": str(real), "__name__": name, "__builtins__": __builtins__}
    orig = pathlib.Path.resolve

    def resolve(self, *a, **k):
        return fake if str(self) == str(real) else orig(self, *a, **k)

    old = sys.argv
    sys.argv = [str(real), *map(str, argv)]
    pathlib.Path.resolve = resolve
    try:
        exec(code, g)
    finally:
        pathlib.Path.resolve = orig
        sys.argv = old
    return g


@pytest.fixture
def root(tmp_path):
    import synth
    return synth.build_root(tmp_path / "proj")
