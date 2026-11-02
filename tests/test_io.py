import gzip

import pytest

from indiagri import io as iio


@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(iio, "DATA", tmp_path / "data")
    monkeypatch.setattr(iio, "CACHE", tmp_path / "cache")
    return tmp_path


def test_write_rows_drops_private_fields_and_flattens(tmp_store):
    rows = [{"id": 1, "name": "Mandi", "Phone": "123", "contact_person": "X", "tags": ["a", "b"], "meta": {"k": 1}}]
    assert iio.write_rows("x/y.csv.gz", rows) == 1
    out = iio.read_rows("x/y.csv.gz")
    assert list(out[0]) == ["id", "name", "tags", "meta"]
    assert out[0]["tags"] == '["a","b"]' and out[0]["meta"] == '{"k":1}'


def test_write_rows_explicit_fields_ignores_extras(tmp_store):
    iio.write_rows("a.csv.gz", [{"a": 1, "b": 2}], ["b", "a"])
    with gzip.open(iio.DATA / "a.csv.gz", "rt") as fh:
        assert fh.read().splitlines() == ["b,a", "2,1"]


def test_cached_calls_function_once(tmp_store):
    calls = []
    fn = lambda: calls.append(1) or {"v": 1}  # noqa: E731
    assert iio.cached("k", fn) == {"v": 1}
    assert iio.cached("k", fn) == {"v": 1}
    assert len(calls) == 1


def test_cached_hashes_long_names(tmp_store):
    iio.cached("n" * 300, lambda: [1])
    assert len(list(iio.CACHE.glob("*.json"))) == 1
    assert len(next(iio.CACHE.glob("*.json")).stem) == 40
