import logging
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.users import Users
from app.core.security import verify_access_token

logger = logging.getLogger("auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Users:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    jwt_token = None

    # 1. Token from HTTPBearer dependency
    if bearer and bearer.credentials:
        jwt_token = bearer.credentials

    # 2. Token from OAuth2PasswordBearer dependency
    if not jwt_token and token:
        jwt_token = token

    # 3. Direct Authorization header inspection (handles cases where headers bypass OpenAPI dependency)
    if not jwt_token:
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header:
            jwt_token = auth_header

    # 4. Fallback to HttpOnly cookie
    if not jwt_token:
        jwt_token = request.cookies.get("access_token")

    # Sanitize token (strip leading 'bearer ', extra whitespace, quotes)
    if jwt_token:
        jwt_token = jwt_token.strip()
        while jwt_token.lower().startswith("bearer "):
            jwt_token = jwt_token[7:].strip()
        jwt_token = jwt_token.strip('"\'')
        if jwt_token in ("undefined", "null", ""):
            jwt_token = None

    if not jwt_token:
        logger.warning(
            f"[Auth] 401 Unauthorized on {request.method} {request.url.path}: "
            f"No token provided in headers or cookies. Headers present: {list(request.headers.keys())}, Cookies: {list(request.cookies.keys())}"
        )
        raise credentials_exception

    payload = verify_access_token(jwt_token)
    if payload is None:
        logger.warning(
            f"[Auth] 401 Unauthorized on {request.method} {request.url.path}: "
            f"Failed to verify JWT signature or token expired. Token prefix: {jwt_token[:15]}..."
        )
        raise credentials_exception

    email: str = payload.get("sub")
    if email is None:
        logger.warning(
            f"[Auth] 401 Unauthorized on {request.method} {request.url.path}: "
            f"Token payload missing 'sub' claim."
        )
        raise credentials_exception

    user = db.query(Users).filter(Users.email_user == email).first()
    if user is None:
        logger.warning(
            f"[Auth] 401 Unauthorized on {request.method} {request.url.path}: "
            f"User '{email}' not found in database."
        )
        raise credentials_exception

    return user
