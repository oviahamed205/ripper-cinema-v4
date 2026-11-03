"""
Unit tests for LAN Broadcast Server.
"""
import unittest
from ripper.broadcast import get_local_ip

class TestLANBroadcast(unittest.TestCase):
    def test_local_ip_detection(self):
        ip = get_local_ip()
        self.assertTrue(isinstance(ip, str))
        self.assertGreater(len(ip), 5)

if __name__ == "__main__":
    unittest.main()
