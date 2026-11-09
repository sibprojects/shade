import pytest

from shade.cost import CostMeter
from shade.models import Usage


def test_cost_of_call_and_total():
    meter = CostMeter({"m": [4.0, 20.0]})
    assert meter.add("m", Usage(1_000_000, 100_000)) == pytest.approx(6.0)
    meter.add("m", Usage(0, 50_000))
    assert meter.total == pytest.approx(7.0)


def test_cache_reads_billed_at_tenth_of_input():
    meter = CostMeter({"m": [4.0, 20.0]})
    assert meter.add("m", Usage(0, 0, 1_000_000)) == pytest.approx(0.4)


def test_unknown_model_costs_zero():
    meter = CostMeter({"m": [4.0, 20.0]})
    assert meter.add("other", Usage(1000, 1000)) == 0.0
    assert meter.total == 0.0
