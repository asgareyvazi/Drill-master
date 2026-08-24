"""Configurable operational standards; never bury policy numbers in UI code."""
import os

def bop_test_interval_days(default=30):
    try:
        return max(1, int(os.getenv("DRILLMASTER_BOP_TEST_INTERVAL_DAYS", default)))
    except (TypeError, ValueError):
        return default
