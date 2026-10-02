"""C-fix Part 1: data/inventory.json can be built from a SAVED pull, with no database connection, and its
snapshot.generated_at is the time of that pull (what index.html's stock panel shows as data_pulled_at).

The saved pull here is a fixture (the real stock from the latest daily snapshot, no backlog, no transfers): the
real backlog and transfer pulls only exist after a live run, so this test shows the mechanism, not real backlog values.
The output goes to a temporary path; data/inventory.json is never touched.
"""
import glob
import json
import os
import subprocess
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

PRICELIST = os.path.join(PROJECT_ROOT, "reference", "pricelist.xlsx")
SNAPSHOTS = sorted(glob.glob(os.path.join(PROJECT_ROOT, "output", "snapshots", "inventory_daily_*.csv")))
pytestmark = [pytest.mark.skipif(os.environ.get("MONTHLY_REFRESH_SANDBOX") == "1", reason="inside a dry-run copy"),
              pytest.mark.skipif(not (os.path.exists(PRICELIST) and SNAPSHOTS), reason="needs reference/pricelist.xlsx and a daily snapshot")]

PULLED_UTC = "2026-10-02T01:12:31Z"

NO_DB = """
import runpy, sys
import db
def refuse(*a, **k):
    raise RuntimeError("DATABASE CONNECTION ATTEMPTED")
db.run_query = refuse
sys.argv = ["build_inventory_dataset.py"] + sys.argv[1:]
runpy.run_path(r"%s", run_name="__main__")
""" % os.path.join(PROJECT_ROOT, "src", "build_inventory_dataset.py")


def _fixture_pull(pull_dir):
    os.makedirs(pull_dir)
    snap = pd.read_csv(SNAPSHOTS[-1])
    inv = pd.DataFrame({"company": "PEM", "warehouse": snap["warehouse"], "itemcode": snap["itemcode"], "unit": "PCS",
                        "stock": snap["stock"], "reserve_bywa": snap["reserve_bywa"], "timestamp": snap["load_timestamp"]})
    inv.to_pickle(os.path.join(pull_dir, "inventory.pkl"))
    pd.DataFrame(columns=["id", "docID", "job", "customer", "itemcode", "quantity", "status", "viewType", "sale_company",
                          "sale_division", "deliverydate", "plan_deliverydate", "receivedate", "backlog_from",
                          "timestamp"]).to_pickle(os.path.join(pull_dir, "backlog_cube.pkl"))
    pd.DataFrame(columns=["ContractID", "ItemCode", "CustomerID", "ForecastDelDate", "PlanDelDate", "ActualQty",
                          "BacklogQty", "Timestamp"]).to_pickle(os.path.join(pull_dir, "backlog_ces.pkl"))
    pd.DataFrame(columns=["itemcode", "ourref", "trans_date", "warehouse", "QtyIn", "QtyOut"]).to_pickle(
        os.path.join(pull_dir, "transfer_pairs.pkl"))
    with open(os.path.join(pull_dir, "pull_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"pulled_at_utc": PULLED_UTC, "pulled_at_local": "2026-10-02 08:12:31"}, f)


def test_inventory_json_is_built_from_a_saved_pull_with_its_pull_time_and_no_connection(tmp_path):
    pull_dir, out = str(tmp_path / "pull"), str(tmp_path / "inventory.json")
    _fixture_pull(pull_dir)
    real_json = os.path.join(PROJECT_ROOT, "data", "inventory.json")
    before = os.path.getmtime(real_json)
    proc = subprocess.run([sys.executable, "-c", NO_DB, "--from-pulls", pull_dir, "--out", out],
                          cwd=os.path.join(PROJECT_ROOT, "src"), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    assert "ATTEMPTED" not in proc.stdout + proc.stderr
    payload = json.load(open(out, encoding="utf-8"))
    assert payload["snapshot"]["generated_at"] == PULLED_UTC, "generated_at must be the pull time, not the build time"
    assert os.path.getmtime(real_json) == before, "the tracked data/inventory.json was touched"


def test_an_incomplete_saved_pull_is_refused(tmp_path):
    import build_inventory_dataset as b
    pull_dir = str(tmp_path / "pull")
    _fixture_pull(pull_dir)
    os.remove(os.path.join(pull_dir, "transfer_pairs.pkl"))
    with pytest.raises(FileNotFoundError, match="transfer_pairs"):
        b.load_pulls(pull_dir)


def test_out_is_refused_without_from_pulls(tmp_path):
    proc = subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "src", "build_inventory_dataset.py"), "--out", str(tmp_path / "x.json")],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode != 0 and "--out is only allowed with --from-pulls" in proc.stderr
