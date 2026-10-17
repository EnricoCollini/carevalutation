"""Independent numerical checks against the example in the published protocol."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from calculator import calculate_evaluation  # noqa: E402


def protocol_example():
    return {
        "vehicle": {
            "condition": "used", "fuel_type": "petrol", "purchase_price": 18000,
            "purchase_fees": 600, "purchase_date": "2026-01-01",
            "registration_date": "2022-01-01", "initial_km": 60000,
            "residual_value": 10000, "residual_source": "Ipotesi del protocollo",
        },
        "usage": {
            "years": 4, "annual_km": 15000,
            "consumption_per_100km": 6, "energy_price": 1.8,
        },
        "insurance": {"channel": "online", "online_annual": 650, "agency_annual": 900},
        "tax": {"annual": 220},
        "tyres": {
            "tier": "base", "base_set_price": 400, "good_set_price": 400,
            "life_km": 30000, "life_years": 10,
            "initial_remaining_km": 30000, "initial_remaining_years": 10,
        },
        "maintenance": {
            "service_cost": 300, "service_interval_km": 15000,
            "service_interval_months": 12,
            "initial_remaining_service_km": 15000,
            "initial_remaining_service_months": 12,
            "repairs_annual": 300,
            "other_annual": 360,
        },
        "revision": {"cost": 80, "last_revision_date": "2025-01-01"},
        "financing": {"enabled": False},
        "budget": {
            "net_monthly_income": 2200, "annual_payments": 12,
            "other_monthly_expenses": 1000, "min_monthly_savings": 200,
            "available_cash": 30000,
        },
    }


class ProtocolExampleTests(unittest.TestCase):
    def test_cash_example(self):
        report = calculate_evaluation(protocol_example())
        summary = report["summary"]
        self.assertAlmostEqual(summary["management_total"], 14760, places=2)
        self.assertAlmostEqual(summary["total_cost"], 23360, places=2)
        self.assertAlmostEqual(summary["monthly_cost"], 486.67, places=2)
        self.assertAlmostEqual(summary["final_km"], 120000, places=0)
        self.assertNotEqual(summary["affordability_label"], "dati_insufficienti")
        self.assertEqual(len([e for e in report["events"] if e["type"] == "revision"]), 2)

    def test_agency_difference(self):
        data = protocol_example()
        data["insurance"]["channel"] = "agency"
        report = calculate_evaluation(data)
        self.assertAlmostEqual(report["summary"]["monthly_cost"], 507.50, places=2)

    def test_financing_example(self):
        data = protocol_example()
        data["financing"] = {
            "enabled": True, "loan_amount": 9000, "down_payment": 9000,
            "term_months": 48, "tan_pct": 7,
        }
        report = calculate_evaluation(data)
        summary = report["summary"]
        self.assertAlmostEqual(summary["credit_cost"], 1344.78, delta=0.05)
        self.assertAlmostEqual(summary["monthly_cost"], 514.68, delta=0.02)
        self.assertAlmostEqual(summary["cash_monthly"], 523.02, delta=0.02)


if __name__ == "__main__":
    unittest.main()
