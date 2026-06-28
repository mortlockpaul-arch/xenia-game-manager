# Retail key
from crypto import CryptoUtils

key = CryptoUtils.get_key()

# HMAC-SHA1
digest = CryptoUtils.hmac_sha1(key, b"Hello World")
print(digest.hex())

# Multiple buffers
digest = CryptoUtils.hmac_sha1_multi(
    key,
    b"Part1",
    b"Part2",
    b"Part3"
)
print(digest.hex())

# RC4 encryption
plaintext = b"Secret Data"

ciphertext = CryptoUtils.rc4(key, plaintext)
print(ciphertext.hex())

# RC4 decryption (same function)
decrypted = CryptoUtils.rc4(key, ciphertext)
print(decrypted)