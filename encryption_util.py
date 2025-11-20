def _xor_cipher(text: str, key: str = "AmitLalJoshi") -> str:
    """Symmetric XOR cipher matching C# InitialDal.Encrypt logic.
    C# uses 1-based index i and i % len(key); when modulo is 0 it maps to key[0].
    It starts with i=1 using key[1], so sequence skips key[0] until i==len(key).
    """
    result_chars = []
    key_len = len(key)
    for i, ch in enumerate(text, start=1):
        mod = i % key_len
        key_char = key[mod] if mod != 0 else key[0]
        result_chars.append(chr(ord(ch) ^ ord(key_char)))
    return ''.join(result_chars)


def decrypt_encrypted_hex(hex_string: str, key: str = "AmitLalJoshi") -> str:
    """Decrypts the stored little-endian UTF-16 hex representation.
    Stored format per char: lowByte highByte (e.g. '/' -> 2F00).
    """
    if len(hex_string) % 4 != 0:
        raise ValueError("Encrypted hex string length must be multiple of 4")
    encrypted_chars = []
    for i in range(0, len(hex_string), 4):
        low = int(hex_string[i:i+2], 16)
        high = int(hex_string[i+2:i+4], 16)
        code_unit = low | (high << 8)
        encrypted_chars.append(chr(code_unit))
    encrypted_text = ''.join(encrypted_chars)
    return _xor_cipher(encrypted_text, key)


def encrypt_to_hex(plain_text: str, key: str = "AmitLalJoshi") -> str:
    """Encrypt plain text to concatenated little-endian UTF-16 hex (lowByte then highByte)."""
    encrypted = _xor_cipher(plain_text, key)
    return ''.join(f"{ord(c) & 0xFF:02X}{(ord(c) >> 8) & 0xFF:02X}" for c in encrypted)


def decrypt_if_encrypted(password: str, key: str = "AmitLalJoshi") -> str:
    """Detect if password is encrypted hex (only hex chars, length multiple of 4).
    If so, decrypt; else return as-is.
    """
    if password and all(c in '0123456789ABCDEFabcdef' for c in password) and len(password) % 4 == 0:
        try:
            return decrypt_encrypted_hex(password, key)
        except Exception:
            return password
    return password

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("Password Encryption/Decryption Utility")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        # Command line argument provided
        input_text = sys.argv[1]
    else:
        # Interactive mode
        print("\nEnter password to encrypt (or encrypted hex to decrypt):")
        input_text = input("> ").strip()
    
    # Detect if input is encrypted (hex) or plain text
    if input_text and all(c in '0123456789ABCDEFabcdef' for c in input_text) and len(input_text) % 4 == 0 and len(input_text) >= 8:
        # Looks like encrypted hex
        try:
            decrypted = decrypt_encrypted_hex(input_text)
            print(f"\n✓ Decrypted password: {decrypted}")
            print(f"  Length: {len(decrypted)} characters")
        except Exception as e:
            print(f"\n✗ Decryption failed: {e}")
            print("  Treating as plain text instead...")
            encrypted = encrypt_to_hex(input_text)
            print(f"\n✓ Encrypted: {encrypted}")
    else:
        # Plain text - encrypt it
        encrypted = encrypt_to_hex(input_text)
        print(f"\n✓ Encrypted: {encrypted}")
        print(f"  Original: {input_text}")
        print(f"  Length: {len(input_text)} characters")
        
        # Verify by decrypting
        verified = decrypt_encrypted_hex(encrypted)
        if verified == input_text:
            print(f"\n✓ Verification successful!")
        else:
            print(f"\n✗ Verification failed!")
    
    print("\n" + "=" * 60)
    print("Decrypted:", decrypt_encrypted_hex(encrypted))
