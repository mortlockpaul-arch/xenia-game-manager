import hashlib
import hmac
from typing import Optional


class CryptoUtils:
    """
    Cryptographic utilities used by Xbox 360 / Xenia.

    Includes:
      - Retail/Devkit keys
      - HMAC-SHA1
      - RC4
    """

    RETAIL_KEY = bytes([
        0xE1, 0xBC, 0x15, 0x9C,
        0x73, 0xB1, 0xEA, 0xE9,
        0xAB, 0x31, 0x70, 0xF3,
        0xAD, 0x47, 0xEB, 0xF3
    ])

    DEVKIT_KEY = bytes([
        0xDA, 0xB6, 0x9A, 0xD9,
        0x8E, 0x28, 0x76, 0x4F,
        0x97, 0x7E, 0xE2, 0x48,
        0x7E, 0x4F, 0x3F, 0x68
    ])

    @staticmethod
    def get_key(devkit: bool = False) -> bytes:
        """
        Returns either the retail or devkit key.
        """
        return CryptoUtils.DEVKIT_KEY if devkit else CryptoUtils.RETAIL_KEY

    @staticmethod
    def hmac_sha1(
        key: bytes,
        data: bytes,
        output_len: int = 16
    ) -> bytes:
        """
        Computes an HMAC-SHA1 over a single buffer.
        """
        digest = hmac.new(key, data, hashlib.sha1).digest()
        return digest[:output_len]

    @staticmethod
    def hmac_sha1_multi(
        key: bytes,
        inp1: bytes,
        inp2: Optional[bytes] = None,
        inp3: Optional[bytes] = None,
        output_len: int = 16
    ) -> bytes:
        """
        Computes an HMAC-SHA1 over multiple buffers without concatenating them.
        Equivalent to the TransformBlock() version in C#.
        """
        h = hmac.new(key, digestmod=hashlib.sha1)

        h.update(inp1)

        if inp2:
            h.update(inp2)

        if inp3:
            h.update(inp3)

        return h.digest()[:output_len]

    @staticmethod
    def rc4(
        key: bytes,
        data: bytes,
        data_offset: int = 0,
        data_len: Optional[int] = None
    ) -> bytes:
        """
        RC4 encryption/decryption.

        RC4 is symmetric, so this function encrypts and decrypts.

        Returns:
            bytes
        """
        if data_len is None:
            data_len = len(data) - data_offset

        # Key Scheduling Algorithm (KSA)
        s = list(range(256))
        j = 0

        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) & 0xFF
            s[i], s[j] = s[j], s[i]

        # Pseudo-Random Generation Algorithm (PRGA)
        i = 0
        j = 0

        out = bytearray(data_len)

        for k in range(data_len):
            i = (i + 1) & 0xFF
            j = (j + s[i]) & 0xFF

            s[i], s[j] = s[j], s[i]

            rnd = s[(s[i] + s[j]) & 0xFF]
            out[k] = data[data_offset + k] ^ rnd

        return bytes(out)