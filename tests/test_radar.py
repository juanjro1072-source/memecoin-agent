import json
import time
import unittest
from pathlib import Path

from radar.__main__ import load_demo_pairs
from radar.scoring import ARCHETYPES, evaluate
from radar.state import ESCALATION_POINTS, AlertMemory


def by_symbol():
    return {v.snap.symbol: v for v in map(evaluate, load_demo_pairs())}


class ScoringTest(unittest.TestCase):
    def test_demo_archetypes(self):
        v = by_symbol()
        self.assertEqual(v["CAPYX"].archetype, ARCHETYPES["COHETE"])
        self.assertEqual(v["TFROG"].archetype, ARCHETYPES["BROTE"])
        self.assertEqual(v["HAMLON"].archetype, ARCHETYPES["CASINO"])
        self.assertEqual(v["SAFEINU"].archetype, ARCHETYPES["TRAMPA"])
        self.assertEqual(v["GRUMP"].archetype, ARCHETYPES["DORMIDO"])

    def test_honeypot_flag(self):
        flags = " ".join(by_symbol()["SAFEINU"].risk_flags)
        self.assertIn("HONEYPOT", flags)

    def test_scores_stay_in_range(self):
        for v in by_symbol().values():
            self.assertTrue(0 <= v.hype <= 100, v.hype)
            self.assertTrue(0 <= v.risk <= 100, v.risk)

    def test_missing_fields_do_not_crash(self):
        v = evaluate({"chainId": "solana", "baseToken": {"symbol": "X"}})
        self.assertEqual(v.snap.symbol, "X")


class MemoryTest(unittest.TestCase):
    def test_alerts_once_then_on_escalation(self):
        m = AlertMemory(None)
        self.assertEqual(m.should_alert("k", 60), "nuevo")
        m.remember("k", 60)
        self.assertIsNone(m.should_alert("k", 60 + ESCALATION_POINTS - 1))
        self.assertTrue(m.should_alert("k", 60 + ESCALATION_POINTS).startswith("escalando"))

    def test_old_entries_expire(self):
        path = Path(self._testMethodName + ".json")
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(json.dumps({"k": {"hype": 90, "ts": time.time() - 2 * 86400}}))
        self.assertEqual(AlertMemory(path).should_alert("k", 10), "nuevo")


if __name__ == "__main__":
    unittest.main()
