from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_SIZE = 4096
PUBLIC_EXPONENT = 65537
PRIVATE_KEY_FILE = 'private_key.pem'
PUBLIC_KEY_FILE = 'public_key.pem'

private_key = rsa.generate_private_key(
    public_exponent=PUBLIC_EXPONENT,
    key_size=KEY_SIZE
)

with open(PRIVATE_KEY_FILE, 'wb') as f:
    f.write(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    )

public_key = private_key.public_key()
with open(PUBLIC_KEY_FILE, 'wb') as f:
    f.write(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )

print(f"Generated keys: {PRIVATE_KEY_FILE}, {PUBLIC_KEY_FILE}")