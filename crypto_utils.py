import os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hmac
from cryptography.hazmat.backends import default_backend


def load_public_key(path: str):
    with open(path, 'rb') as f:
        return serialization.load_pem_public_key(f.read())


def load_private_key(path: str):
    with open(path, 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def encrypt_file(input_file: str, public_key_path: str) -> str:
    with open(input_file, 'rb') as f:
        data = f.read()

    aes_key = os.urandom(32)
    iv = os.urandom(16)

    cipher = Cipher(algorithms.AES(aes_key), modes.CFB(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(data) + encryptor.finalize()

    public_key = load_public_key(public_key_path)

    encrypted_key = public_key.encrypt(
        aes_key + iv,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    h = hmac.HMAC(aes_key, hashes.SHA256(), backend=default_backend())
    h.update(ciphertext)
    tag = h.finalize()

    # write out: encrypted_key length (4 bytes big endian) || encrypted_key || ciphertext || tag
    encrypted_path = input_file + '.enc'
    with open(encrypted_path, 'wb') as f:
        f.write(len(encrypted_key).to_bytes(4, 'big'))
        f.write(encrypted_key)
        f.write(ciphertext)
        f.write(tag)

    return encrypted_path


def decrypt_file(encrypted_file: str, private_key_path: str) -> str:
    with open(encrypted_file, 'rb') as f:
        content = f.read()

    # parse lengths
    key_len = int.from_bytes(content[:4], 'big')
    offset = 4
    encrypted_key = content[offset:offset + key_len]
    offset += key_len
    # ciphertext until last 32 bytes (HMAC-SHA256 tag)
    ciphertext = content[offset:-32]
    tag = content[-32:]

    private_key = load_private_key(private_key_path)

    # decrypt AES key + IV
    aes_key_iv = private_key.decrypt(
        encrypted_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    aes_key = aes_key_iv[:32]
    iv = aes_key_iv[32:]

    # verify HMAC
    h = hmac.HMAC(aes_key, hashes.SHA256(), backend=default_backend())
    h.update(ciphertext)
    try:
        h.verify(tag)
    except Exception:
        raise ValueError("HMAC verification failed! Data is corrupted or tampered with.")

    # decrypt
    cipher = Cipher(algorithms.AES(aes_key), modes.CFB(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # write
    if encrypted_file.endswith('.enc'):
        output_file = encrypted_file[:-4]
    else:
        output_file = encrypted_file + '.dec'

    with open(output_file, 'wb') as f:
        f.write(plaintext)

    return output_file
