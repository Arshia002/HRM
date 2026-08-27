import unittest

from sazmanhr.security import hash_password, normalize_username, totp_code, verify_password, verify_totp


class SecurityTests(unittest.TestCase):
    def test_password_round_trip(self):
        encoded = hash_password("A-strong-password-1400")
        self.assertTrue(verify_password("A-strong-password-1400", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))
        self.assertNotIn("A-strong-password-1400", encoded)

    def test_username_normalization(self):
        self.assertEqual(normalize_username(" Owner.Test "), "owner.test")
        with self.assertRaises(ValueError):
            normalize_username("ab")

    def test_weak_password_is_rejected(self):
        with self.assertRaises(ValueError):
            hash_password("123456")

    def test_totp_vector_and_window(self):
        secret = "JBSWY3DPEHPK3PXP"
        code = totp_code(secret, when=1_700_000_000)
        self.assertTrue(verify_totp(secret, code, when=1_700_000_000))
        self.assertFalse(verify_totp(secret, "000000", when=1_700_000_000))


if __name__ == "__main__":
    unittest.main()
