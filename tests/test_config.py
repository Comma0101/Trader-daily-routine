import unittest

from config import FUTURES_UNIVERSE


class FuturesUniverseConfigTests(unittest.TestCase):
    def test_nq_and_ym_use_live_tff_contract_codes(self):
        self.assertEqual(FUTURES_UNIVERSE["NQ"]["cot_code"], "209742")
        self.assertEqual(FUTURES_UNIVERSE["YM"]["cot_code"], "124603")
