"""Run the real orchestrator/math without external DB or coupon redemption writes."""
import ast
import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def evaluate(coupons, entered='WELCOME', excluded=None, cap=70, items=None):
    source = Path(__file__).parents[1] / 'routes/coupons.py'
    names = {'evaluate_cart_promotions', '_compute_discount', 'fold_code',
             '_item_category_set', '_item_in_scope'}
    nodes = [n for n in ast.parse(source.read_text()).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert len(nodes) == len(names)
    class Cursor:
        def __aiter__(self):
            async def rows():
                for c in coupons:
                    if c.get('auto_apply'):
                        yield c
            return rows()
    db = SimpleNamespace(settings=SimpleNamespace(find_one=AsyncMock(return_value={})),
                         coupons=SimpleNamespace(find=lambda *a: Cursor()))
    scope = {'db': db, 're': re, '_promo_cap_pct': AsyncMock(return_value=cap),
             '_log_coupon_attempt': AsyncMock()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
    async def enrich(value):
        return value
    async def validate(c, total, lines, *args):
        return {'valid': True, 'discount': scope['_compute_discount'](c, total, lines),
                'free_shipping': c.get('free_shipping', False)}
    async def resolve(code):
        c = next((c for c in coupons if c['code'] == code), None)
        return c, code
    scope.update(_enrich_items_category_ids=enrich, _evaluate_single=validate, resolve_coupon_code=resolve)
    return asyncio.run(scope['evaluate_cart_promotions'](
        3790, items or [{'product_id': 'p', 'price': 3790, 'qty': 1}],
        entered_code=entered, excluded_ids=excluded))


def campaign(cid, value, **kwargs):
    return {'id': cid, 'code': cid, 'type': 'percent', 'value': value,
            'auto_apply': True, 'combinable': True, **kwargs}


def pair(**welcome):
    return [campaign('LAUNCH', 20), campaign('WELCOME', 10, first_order_only=True, **welcome)]


@pytest.mark.parametrize('entered', ['WELCOME', ''])
def test_launch_before_welcome_even_when_welcome_has_higher_priority(entered):
    r = evaluate(pair(priority=100), entered)
    assert [(a['code'], a['discount']) for a in r['applied']] == [('LAUNCH', 758), ('WELCOME', 303.2)]
    assert r['total_discount'] == 1061.2
    net = round(3790 - r['total_discount'], 2)
    bank = round(net * .05, 2)
    assert bank == 136.44
    assert round(net - bank + 99, 2) == 2691.36


def test_entered_coupon_still_wins_noncombinable_selection():
    r = evaluate(pair(combinable=False))
    assert [(a['code'], a['discount']) for a in r['applied']] == [('WELCOME', 379)]
    assert not r['rejected']


def test_one_sided_permission_and_group_exclusion_preserved():
    coupons = pair(combinable_with=['LAUNCH'])
    assert len(evaluate(coupons)['applied']) == 2
    for c in coupons:
        c['stack_group'] = 'only-one'
    assert [a['code'] for a in evaluate(coupons)['applied']] == ['WELCOME']


def test_removed_campaign_not_subtracted_and_zero_shipping_processed_last():
    coupons = pair() + [campaign('SHIPPING', 0, free_shipping=True, min_cart_total=3000, priority=999)]
    assert [a['code'] for a in evaluate(coupons)['applied']] == ['LAUNCH', 'WELCOME']
    r = evaluate(coupons, excluded=['LAUNCH'])
    assert [(a['code'], a['discount']) for a in r['applied']] == [('WELCOME', 379), ('SHIPPING', 0)]


def test_scoped_campaign_then_coupon_and_cap_reconcile():
    coupons = pair()
    coupons[0]['products'] = ['p']
    lines = [{'product_id': 'p', 'price': 2000, 'qty': 1}, {'product_id': 'q', 'price': 1790, 'qty': 1}]
    r = evaluate(coupons, items=lines)
    assert [a['discount'] for a in r['applied']] == [400, 339]
    capped = evaluate(coupons, cap=10, items=lines)
    assert capped['capped']
    assert round(sum(a['discount'] for a in capped['applied']), 2) == capped['total_discount'] == 379
