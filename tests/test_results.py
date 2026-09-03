import pytest

from geoflow.results import parse_output, summarize


def test_weighted_means_and_filters():
    r = {"run_id": "test", "dataset": {"month": "2025-01", "rows": 12, "source": "test"},
         "valid_rows": 11, "rejected_rows": 1, "rejected": {"Malformed": 1}, "metadata": {},
         "days": [], "od": [], "zone_hours": [
             {"zone": 1, "hour": 8, "values": [1, 1000, 60, 100]},
             {"zone": 1, "hour": 9, "values": [9, 90000, 5400, 9000]},
             {"zone": 2, "hour": 8, "values": [1, 2000, 120, 200]}]}
    info = {1: {"name": "A", "borough": "A"}, 2: {"name": "B", "borough": "B"}}
    selected = summarize(r, info, borough="A")
    assert selected["summary"]["trips"] == 10
    assert selected["summary"]["avg_minutes"] == 9.1
    assert summarize(r, info, hour=8)["summary"]["trips"] == 2
    assert summarize(r, info, hour=22)["summary"]["avg_minutes"] == 0
    assert selected["quality"]["input"] == 12  # Quality remains full-dataset scope.


def test_duplicate_reduce_keys_cannot_be_published(tmp_path):
    path = tmp_path / "bad.tsv"
    path.write_text("Z|001|00\t1,1,1,1\nZ|001|00\t1,1,1,1\n")
    with pytest.raises(ValueError, match="Duplicate"):
        parse_output(path)
