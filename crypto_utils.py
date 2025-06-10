import os
import hashlib
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def _derive_keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=64,
        salt=salt,
        iterations=200_000,
        backend=default_backend()
    )
    full_key = kdf.derive(password.encode())
    return full_key[:32], full_key[32:]


def encrypt_file(input_file: str, password: str) -> str:
    with open(input_file, 'rb') as f:
        data = f.read()

    salt = os.urandom(16)
    enc_key, hmac_key = _derive_keys(password, salt)

    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(enc_key), modes.CFB(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(data) + encryptor.finalize()

    h = hmac.HMAC(hmac_key, hashes.SHA256(), backend=default_backend())
    h.update(salt + iv + ciphertext)
    tag = h.finalize()

    encrypted_path = input_file + '.enc'
    with open(encrypted_path, 'wb') as f:
        f.write(salt + iv + ciphertext + tag)

    return encrypted_path


def decrypt_file(encrypted_file: str, password: str) -> str:
    with open(encrypted_file, 'rb') as f:
        payload = f.read()

    salt = payload[:16]
    iv = payload[16:32]
    tag = payload[-32:]
    ciphertext = payload[32:-32]

    enc_key, hmac_key = _derive_keys(password, salt)

    h = hmac.HMAC(hmac_key, hashes.SHA256(), backend=default_backend())
    h.update(salt + iv + ciphertext)
    try:
        h.verify(tag)
    except Exception:
        raise ValueError("HMAC verification failed! Data is corrupted or tampered with.")

    cipher = Cipher(algorithms.AES(enc_key), modes.CFB(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    if encrypted_file.endswith('.enc'):
        output_file = encrypted_file[:-4]
    else:
        output_file = encrypted_file + '.dec'

    with open(output_file, 'wb') as f:
        f.write(plaintext)

    return output_file


if __name__ == '__main__':
    test_file = 'test.txt'
    password = 'my_secure_password'

    print(f"Encrypting {test_file}...")
    encrypted_path = encrypt_file(test_file, password)
    print(f"Encrypted file created: {encrypted_path}")

    os.remove(test_file)
    print(f"Original file {test_file} deleted.")

    print(f"Decrypting {encrypted_path}...")
    decrypted_path = decrypt_file(encrypted_path, password)
    print(f"Decrypted file created: {decrypted_path}")

    os.remove(encrypted_path)
    print(f"Encrypted file {test_file} deleted.")
