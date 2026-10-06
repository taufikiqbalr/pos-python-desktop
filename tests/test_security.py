import unittest

from app.security import hash_password, verify_password


class SecurityTests(unittest.TestCase):
    def test_password_roundtrip(self):
        encoded = hash_password("secret")
        self.assertTrue(verify_password("secret", encoded))
        self.assertFalse(verify_password("wrong", encoded))


if __name__ == "__main__":
    unittest.main()
