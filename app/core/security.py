import os
import pyotp

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from jose import jwt, JWTError
from passlib.context import CryptContext

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Get pasword hash and come back at BD"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if the password makes match with hashed password"""
    return pwd_context.verify(plain_password, hashed_password)


# CREATE TOKEN JWT


def create_access_token(data: dict, expire_delta: timedelta | None = None) -> str:
    """Generate a JWT token with expiration date"""
    to_encode = data.copy()

    if expire_delta:
        expire = datetime.now(timezone.utc) + expire_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str) -> dict | None:
    """Verify the JWT token is valid and return payload"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# TOTP functions


def generate_totp_secret() -> str:
    """Returns a random Base32 secret string."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    """Builds the `otpauth://` URI with issuer name "FinancialDashboard"."""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email, issuer_name="FinancialDashboard"
    )


def verify_totp_code(secret: str, code: str) -> bool:
    """Verifies the 6-digit TOTP token against the user's secret."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)
