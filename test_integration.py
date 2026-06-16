import requests
import unittest
import time

BASE_URL = "http://127.0.0.1:8000"

class TestSysMonAgent(unittest.TestCase):
    def test_01_get_logs(self):
        r = requests.get(f"{BASE_URL}/api/logs")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_02_create_and_delete_log(self):
        # Create a log with custom past date-time
        payload = {
            "type": "incident",
            "component": "test-gateway",
            "severity": "high",
            "status": "resolving",
            "content": "Test log integration content",
            "created_at": "2026-06-15 12:34:56"
        }
        r = requests.post(f"{BASE_URL}/api/logs", json=payload)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        log_id = data.get("id")
        self.assertTrue(log_id.startswith("log-"))
        self.assertEqual(data.get("created_at"), "2026-06-15 12:34:56")

        # Update the log
        update_payload = {
            "type": "incident",
            "component": "test-gateway",
            "severity": "high",
            "status": "resolved",
            "content": "Test log integration content updated",
            "created_at": "2026-06-15 12:34:56"
        }
        r_up = requests.put(f"{BASE_URL}/api/logs/{log_id}", json=update_payload)
        self.assertEqual(r_up.status_code, 200)
        data_up = r_up.json()
        self.assertEqual(data_up.get("status"), "resolved")
        self.assertIsNotNone(data_up.get("resolved_at"))

        # Clean up / Delete
        r_del = requests.delete(f"{BASE_URL}/api/logs/{log_id}")
        self.assertEqual(r_del.status_code, 200)

    def test_03_get_sops(self):
        r = requests.get(f"{BASE_URL}/api/sops")
        self.assertEqual(r.status_code, 200)
        sops = r.json()
        self.assertIsInstance(sops, list)
        # Verify the bank maintenance SOP is present
        titles = [s.get("title") for s in sops]
        self.assertIn("Bảo trì cổng thanh toán bank", titles)

    def test_04_create_and_delete_sop_manual(self):
        payload = {
            "title": "Quy trình test tự động",
            "content": "Nội dung quy trình test tự động 1 -> 2 -> 3"
        }
        r = requests.post(f"{BASE_URL}/api/sops", json=payload)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("status"), "success")
        sop = data.get("data")
        sop_id = sop.get("id")
        self.assertTrue(sop_id.startswith("sop-"))
        self.assertEqual(sop.get("title"), "Quy trình test tự động")

        # Get SOPs and verify it's there
        r_list = requests.get(f"{BASE_URL}/api/sops")
        titles = [s.get("title") for s in r_list.json()]
        self.assertIn("Quy trình test tự động", titles)

        # Delete SOP
        r_del = requests.delete(f"{BASE_URL}/api/sops/{sop_id}")
        self.assertEqual(r_del.status_code, 200)

if __name__ == "__main__":
    unittest.main()
