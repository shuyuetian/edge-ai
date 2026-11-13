"""窗口构建的本地单元测试。"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from skab_dataset import SENSOR_COLUMNS, build_windows, prepare_segments


def make_frame(values: list[float], labels: list[int]) -> pd.DataFrame:
    length = len(values)
    frame = pd.DataFrame(
        {
            "datetime": pd.date_range("2026-01-01", periods=length, freq="1s"),
            "anomaly": labels,
            "changepoint": [0] * length,
        }
    )
    for column in SENSOR_COLUMNS:
        frame[column] = np.asarray(values, dtype=np.float32)
    return frame


class WindowTests(unittest.TestCase):
    def test_endpoint_label_and_shape(self) -> None:
        frame = make_frame(list(range(12)), [0] * 9 + [1] * 3)
        windows = build_windows(prepare_segments(frame), window_size=4, stride=2)
        self.assertEqual(windows.x.shape, (5, 4, len(SENSOR_COLUMNS)))
        np.testing.assert_array_equal(windows.anomaly, np.array([0, 0, 0, 1, 1]))
        self.assertTrue(np.all(windows.x[:, -1, 0] == np.array([3, 5, 7, 9, 11])))

    def test_long_gap_breaks_windows(self) -> None:
        first = make_frame([1, 2, 3, 4], [0, 0, 0, 0])
        second = make_frame([5, 6, 7, 8], [1, 1, 1, 1])
        second["datetime"] = second["datetime"] + pd.Timedelta(seconds=10)
        frame = pd.concat([first, second], ignore_index=True)
        segments = prepare_segments(frame, max_gap_seconds=2.0)
        self.assertEqual(len(segments), 2)
        windows = build_windows(segments, window_size=4, stride=1)
        self.assertEqual(len(windows.x), 2)
        np.testing.assert_array_equal(windows.anomaly, np.array([0, 1]))

    def test_two_second_gap_is_interpolated(self) -> None:
        frame = make_frame([1, 2, 3, 4, 5], [0, 0, 0, 0, 0])
        frame.loc[3:, "datetime"] += pd.Timedelta(seconds=1)
        segments = prepare_segments(frame, max_gap_seconds=2.0)
        self.assertEqual(len(segments), 1)
        self.assertEqual(len(segments[0]), 6)
        self.assertTrue(segments[0][SENSOR_COLUMNS].notna().all().all())


if __name__ == "__main__":
    unittest.main()
