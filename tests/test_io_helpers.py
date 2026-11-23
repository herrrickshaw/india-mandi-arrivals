import gzip
import hashlib
import json

import pytest

from indiagri import io as iio


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(iio, "DATA", tmp_path / "data")
    monkeypatch.setattr(iio, "CACHE", tmp_path / ".cache")
    return tmp_path


def test_write_rows_union_of_keys_in_first_seen_order_and_count(tmp_path):
    n = iio.write_rows("a/b/x.csv.gz", [{"a": 1, "b": 2}, {"b": 3, "c": 4}])
    assert n == 2
    with gzip.open(tmp_path / "data/a/b/x.csv.gz", "rt", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert lines == ["a,b,c", "1,2,", ",3,4"]


def test_write_rows_drops_private_fields_case_insensitively_by_substring(tmp_path):
    iio.write_rows("x.csv.gz", [{"Phone_No": "999", "name": "m", "contact_person": "x", "officer_name": "y", "ok": 1}])
    assert iio.read_rows("x.csv.gz") == [{"name": "m", "ok": "1"}]


def test_write_rows_explicit_fields_ignore_extras_and_keep_order():
    iio.write_rows("x.csv.gz", [{"a": 1, "b": 2, "z": 9}], fields=["b", "a"])
    assert iio.read_rows("x.csv.gz") == [{"b": "2", "a": "1"}]


def test_write_rows_flattens_nested_values_to_compact_json():
    iio.write_rows("x.csv.gz", [{"d": {"k": [1, "é"]}, "l": [1, 2]}])
    row = iio.read_rows("x.csv.gz")[0]
    assert row["d"] == '{"k":[1,"é"]}'
    assert row["l"] == "[1,2]"


def test_write_rows_empty_writes_header_only_and_returns_zero():
    assert iio.write_rows("x.csv.gz", [], fields=["a"]) == 0
    assert iio.read_rows("x.csv.gz") == []


def test_write_rows_accepts_generator():
    assert iio.write_rows("g.csv.gz", ({"a": i} for i in range(3))) == 3


def test_cached_runs_once_then_reads_json(tmp_path):
    calls = []

    def fn():
        calls.append(1)
        return {"v": [1, 2], "t": "é"}

    assert iio.cached("k", fn) == {"v": [1, 2], "t": "é"}
    assert iio.cached("k", fn) == {"v": [1, 2], "t": "é"}
    assert len(calls) == 1
    assert (tmp_path / ".cache/k.json").exists()


def test_cached_long_names_are_hashed_and_boundary_is_120(tmp_path):
    short = "a" * 119
    iio.cached(short, lambda: 1)
    assert (tmp_path / ".cache" / f"{short}.json").exists()
    long = "b" * 120
    iio.cached(long, lambda: 2)
    assert (tmp_path / ".cache" / (hashlib.sha1(long.encode()).hexdigest() + ".json")).exists()
    assert not (tmp_path / ".cache" / f"{long}.json").exists()


def test_cached_does_not_cache_exceptions(tmp_path):
    def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        iio.cached("k", boom)
    assert not (tmp_path / ".cache/k.json").exists()
    assert iio.cached("k", lambda: [3]) == [3]
    assert json.loads((tmp_path / ".cache/k.json").read_text()) == [3]
