from __future__ import annotations

import unittest

from analyze_board_results import parse_environment


class AnalyzeBoardResultsTests(unittest.TestCase):
    def test_parses_scaling_governor_lines(self):
        environment = """===== 开发板型号 =====
Rockchip RK3566 OPi 3B

===== 操作系统 =====
PRETTY_NAME="Orange Pi 1.0.8 Bookworm"

===== CPU =====
Model name:                      Cortex-A55

===== 内存 =====
               total        used        free
Mem:           3.8Gi       194Mi       3.4Gi

===== CPU 频率策略 =====
cpu0 scaling_governor=performance scaling_min_freq=408000 scaling_max_freq=1800000 scaling_cur_freq=1800000
cpu1 scaling_governor=performance scaling_min_freq=408000 scaling_max_freq=1800000 scaling_cur_freq=1800000

===== 温度 =====
thermal_zone0 type=soc-thermal temp_millidegree_c=40625
"""

        result = parse_environment(environment)

        self.assertEqual(result["governors"], ["performance"])
        self.assertEqual(
            result["current_frequency_mhz"],
            {"min": 1800.0, "max": 1800.0},
        )
        self.assertEqual(result["max_temperature_c"], 40.625)


if __name__ == "__main__":
    unittest.main()
