"""Günlük çağrı sınırı testleri."""
from datetime import date

import pytest

import quota


@pytest.fixture(autouse=True)
def clean():
    quota.reset()
    yield
    quota.reset()


def test_no_limit_always_allows():
    assert all(quota.take(0) for _ in range(100))


def test_blocks_after_limit():
    day = date(2026, 11, 20)
    assert [quota.take(2, day) for _ in range(4)] == [True, True, False, False]


def test_new_day_resets():
    assert quota.take(1, date(2026, 11, 20))
    assert not quota.take(1, date(2026, 11, 20))
    assert quota.take(1, date(2026, 11, 21))
