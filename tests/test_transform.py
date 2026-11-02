from indiagri import transform as tf


def test_months_crosses_year_boundary():
    assert list(tf.months("2025-11", "2026-02")) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]
    assert list(tf.months("2026-03", "2026-02")) == []


def test_chunked():
    assert tf.chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert tf.chunked([], 3) == []


def test_real_commodity_ids_drops_pseudo_and_junk():
    rows = [{"cmdt_id": "1"}, {"id": 2}, {"cmdt_id": "0"}, {"cmdt_id": "9999"}, {"cmdt_id": "x"}, {"id": "5"}, {"cmdt_id": 1}]
    assert tf.real_commodity_ids(rows) == [1, 2, 5]


def test_merge_state_monthly_keys_on_name_because_arrivals_lack_id():
    out = {}
    price = [{"cmdt_id": 7, "cmdt_name": " Wheat ", "cmdt_grp_name": "Cereals", "state_name": " Punjab ", "as_on": 2400}]
    arrival = [{"cmdt_name": "Wheat", "state_name": "Punjab", "as_on": 1500.5}]   # no cmdt_id
    tf.merge_state_monthly(out, 2026, 3, "price", price)
    tf.merge_state_monthly(out, 2026, 3, "arrival", arrival)
    assert list(out) == [("2026-03", "Wheat", "Punjab")]
    assert out[("2026-03", "Wheat", "Punjab")] == {
        "month": "2026-03", "commodity_id": 7, "commodity": "Wheat", "group": "Cereals",
        "state": "Punjab", "price_rs_qtl": 2400, "arrivals_t": 1500.5}


def test_arrival_only_row_keeps_commodity_id_none():
    out = {}
    tf.merge_state_monthly(out, 2026, 1, "arrival", [{"cmdt_name": "Onion", "state_name": "Goa", "as_on": 3}])
    assert out[("2026-01", "Onion", "Goa")]["commodity_id"] is None


def test_sorted_state_monthly_orders_by_commodity_state_month():
    out = {}
    for ym, c, s in [("2026-02", "B", "X"), ("2026-01", "B", "X"), ("2026-01", "A", "Z"), ("2026-01", "A", "Y")]:
        out[(ym, c, s)] = {"month": ym, "commodity": c, "state": s}
    assert [(r["commodity"], r["state"], r["month"]) for r in tf.sorted_state_monthly(out)] == [
        ("A", "Y", "2026-01"), ("A", "Z", "2026-01"), ("B", "X", "2026-01"), ("B", "X", "2026-02")]


def test_reported_markets_and_sample_row():
    recs = [{"status": "Reported Markets", "cmdt_name": "Wheat", "arrival_qty": 4.5, "modal_price_wt": 2000},
            {"status": "Non Reported Markets", "cmdt_name": "Rice"}]
    kept = tf.reported_markets(recs)
    assert len(kept) == 1
    row = tf.market_sample_row("2026-01-01", kept[0])
    assert row["date"] == "2026-01-01" and row["arrival_t"] == 4.5 and row["modal_price_rs_qtl"] == 2000
    assert list(row) == ["date", "commodity", "state", "district", "market", "mkt_id", "arrival_t", "modal_price_rs_qtl"]


def test_flatten_districts_accepts_both_key_spellings():
    states = [{"state_id": 19, "state_name": "MP", "districts": [{"district_id": 1}, {"district_id": 2}]},
              {"id": 5, "name": "X", "districts": [{"district_id": 9}]}, {"id": 6, "districts": None}]
    rows = tf.flatten_districts(states)
    assert [(r["state_id"], r["state_name"], r["district_id"]) for r in rows] == [(19, "MP", 1), (19, "MP", 2), (5, "X", 9)]


def test_first_list_value():
    assert tf.first_list_value({"a": 1, "b": [1, 2]}) == [1, 2]
    assert tf.first_list_value({"a": 1}) == [{"a": 1}]
    assert tf.first_list_value([3]) == [3]


def test_dedupe_fci_drops_percent_rows_and_overlap():
    rows = [{"statename": "A", "cropname": "Rice", "years": "2016-17"},
            {"statename": "A", "cropname": "Rice", "years": "2016-17"},
            {"statename": "A", "cropname": "Rice", "years": "% Change in 2016-17"},
            {"statename": "A", "cropname": "Rice", "years": "2017-18"}]
    assert [r["years"] for r in tf.dedupe_fci(rows)] == ["2016-17", "2017-18"]
