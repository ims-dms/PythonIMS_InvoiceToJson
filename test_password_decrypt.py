import unittest
from encryption_util import encrypt_to_hex, decrypt_encrypted_hex, decrypt_if_encrypted

class TestPasswordEncryption(unittest.TestCase):
    def test_encrypt_matches_expected(self):
        self.assertEqual(encrypt_to_hex("Bizu123"), "2F0000000E00390050005E007900")

    def test_decrypt_roundtrip(self):
        enc = encrypt_to_hex("Bizu123")
        dec = decrypt_encrypted_hex(enc)
        self.assertEqual(dec, "Bizu123")

    def test_auto_detection(self):
        self.assertEqual(decrypt_if_encrypted("2F0000000E00390050005E007900"), "Bizu123")
        # Non-hex should return as-is
        self.assertEqual(decrypt_if_encrypted("plainpass"), "plainpass")

if __name__ == '__main__':
    unittest.main()
