"""模型结构测试。"""

from __future__ import annotations

import unittest

import torch

from train_model import AnomalyCNN


class ModelTests(unittest.TestCase):
    def test_output_shape(self) -> None:
        model = AnomalyCNN(channels=8)
        output = model(torch.zeros(4, 60, 8, dtype=torch.float32))
        self.assertEqual(tuple(output.shape), (4,))
        self.assertEqual(sum(p.numel() for p in model.parameters()), 8609)


if __name__ == "__main__":
    unittest.main()
