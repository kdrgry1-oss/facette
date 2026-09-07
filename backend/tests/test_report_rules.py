import importlib.util
from pathlib import Path
import sys
import types


# Load the pure aggregation helpers without importing routes/__init__.py (which
# intentionally registers the complete FastAPI application dependency graph).
routes_pkg = types.ModuleType("routes")
routes_pkg.__path__ = []
deps_stub = types.ModuleType("routes.deps")
deps_stub.db = object()
sys.modules.setdefault("routes", routes_pkg)
sys.modules.setdefault("routes.deps", deps_stub)
spec = importlib.util.spec_from_file_location(
    "routes.report_dedup", Path(__file__).parents[1] / "routes" / "report_dedup.py"
)
report_dedup = importlib.util.module_from_spec(spec)
sys.modules["routes.report_dedup"] = report_dedup
spec.loader.exec_module(report_dedup)
canonical_order_stages = report_dedup.canonical_order_stages
effective_order_date_match = report_dedup.effective_order_date_match
split_confirmed_return = report_dedup.split_confirmed_return


def test_effective_date_prefers_marketplace_and_falls_back_only_when_empty():
    match = effective_order_date_match("2026-08-01", "2026-08-31")
    assert match["$or"][0] == {
        "marketplace_order_date": {"$gte": "2026-08-01", "$lte": "2026-08-31"}
    }
    assert match["$or"][1] == {
        "marketplace_order_date": {"$in": [None, ""]},
        "created_at": {"$gte": "2026-08-01", "$lte": "2026-08-31"},
    }


def test_canonical_order_preference_is_terminal_partial_then_newest():
    stages = canonical_order_stages()
    assert [next(iter(stage)) for stage in stages] == [
        "$addFields", "$addFields", "$sort", "$group", "$replaceRoot"
    ]
    sort = stages[2]["$sort"]
    assert sort["_report_terminal"] == -1
    assert sort["_report_partial_cancel"] == -1
    assert sort["updated_at"] == -1


def test_empty_order_number_uses_internal_identity():
    key = canonical_order_stages()[1]["$addFields"]["_report_dedupe_key"]
    assert key["$cond"][1] == {"$concat": ["order:", "$_report_order_number"]}
    assert key["$cond"][2]["$concat"][0] == "id:"


def test_confirmed_return_is_removed_from_net_but_cancel_is_not_in_denominator():
    net_qty, net_amount, return_qty, return_amount = split_confirmed_return(8, 800.0, 4)
    assert (net_qty, net_amount, return_qty, return_amount) == (4, 400.0, 4, 400.0)
    assert return_qty / (net_qty + return_qty) * 100 == 50.0


def test_confirmed_return_cannot_exceed_sold_quantity():
    assert split_confirmed_return(2, 300.0, 9) == (0, 0.0, 2, 300.0)
