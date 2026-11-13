from __future__ import annotations

import copy
import unittest

from compare_performance import (
    ComparisonError,
    compare_metrics,
    validate_comparison,
)


def make_analysis(mean_ms: float = 10.0) -> dict:
    return {
        "run_id": "test",
        "host_arch": "aarch64",
        "qemu": "not_used",
        "iterations": 1000,
        "warmup": 30,
        "rounds": 5,
        "median_metrics": {
            "mean_ms": mean_ms,
            "p50_ms": 9.5,
            "p95_ms": 12.0,
            "p99_ms": 13.0,
            "min_ms": 8.0,
            "max_ms": 14.0,
            "peak_rss_kib": 16000.0,
        },
        "environment_before": {
            "board_model": "Orange Pi 3B",
            "cpu_model": "Cortex-A55",
            "os": "Debian 12",
            "governors": ["schedutil"],
        },
    }


class ComparePerformanceTests(unittest.TestCase):
    def test_same_result_passes(self):
        baseline = make_analysis()
        candidate = copy.deepcopy(baseline)
        warnings = validate_comparison(baseline, candidate, False, False)
        comparisons = compare_metrics(
            baseline,
            candidate,
            {
                "max_mean_regression_pct": 10.0,
                "max_p95_regression_pct": 10.0,
                "max_rss_regression_pct": 10.0,
            },
        )
        self.assertEqual(warnings, [])
        self.assertFalse(any(item["regressed"] for item in comparisons))

    def test_detects_mean_regression(self):
        baseline = make_analysis(10.0)
        candidate = make_analysis(11.5)
        comparisons = compare_metrics(
            baseline,
            candidate,
            {
                "max_mean_regression_pct": 10.0,
                "max_p95_regression_pct": 10.0,
                "max_rss_regression_pct": 10.0,
            },
        )
        mean = next(item for item in comparisons if item["metric"] == "mean_ms")
        self.assertAlmostEqual(mean["change_pct"], 15.0)
        self.assertTrue(mean["regressed"])

    def test_rejects_different_rounds(self):
        baseline = make_analysis()
        candidate = make_analysis()
        candidate["rounds"] = 3
        with self.assertRaisesRegex(ComparisonError, "rounds"):
            validate_comparison(baseline, candidate, False, False)

    def test_rejects_qemu_without_override(self):
        baseline = make_analysis()
        baseline["host_arch"] = "x86_64"
        baseline["qemu"] = "qemu-aarch64"
        with self.assertRaisesRegex(ComparisonError, "QEMU"):
            validate_comparison(baseline, make_analysis(), False, False)
        warnings = validate_comparison(
            baseline, make_analysis(), True, False
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("QEMU", warnings[0])

    def test_rejects_environment_change_by_default(self):
        baseline = make_analysis()
        candidate = make_analysis()
        candidate["environment_before"]["governors"] = ["performance"]
        with self.assertRaisesRegex(ComparisonError, "运行环境不一致"):
            validate_comparison(baseline, candidate, False, False)
        warnings = validate_comparison(baseline, candidate, False, True)
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
