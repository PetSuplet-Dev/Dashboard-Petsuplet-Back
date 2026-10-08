from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.users import Users
from app.core.security import (
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code,
    create_access_token,
)
from app.api.dependencies import get_current_user
from app.schemas.users import TotpRequest
from app.config import settings
import qrcode
import io
import base64

router = APIRouter()


class VerifyTotpRequest(BaseModel):
    email: str
    code: str


@router.post("/setup")
def totp_setup(
    db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)
):
    if current_user.is_totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP is already enabled.",
        )

    if not current_user.totp_secret:
        current_user.totp_secret = generate_totp_secret()
        db.commit()

    totp_uri = get_totp_uri(current_user.totp_secret, current_user.email_user)

    # Generate QR code
    img = qrcode.make(totp_uri)
    buf = io.BytesIO()
    img.save(buf)
    qr_code_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "qr_code": f"data:image/png;base64,{qr_code_b64}",
        "secret": current_user.totp_secret,
    }


@router.post("/enable")
def totp_enable(
    request: TotpRequest,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP secret not found.",
        )

    if not verify_totp_code(current_user.totp_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code.",
        )

    current_user.is_totp_enabled = True
    db.commit()

    return {
        "status": "TOTP enabled successfully.",
        "user": current_user,
    }


@router.post("/verify-totp")
def verify_totp(
    request: VerifyTotpRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(Users).filter(Users.email_user == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.totp_secret and not user.is_totp_enabled:
        user.is_totp_enabled = True
        db.commit()

    if not user.is_totp_enabled or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP not enabled for this user.",
        )

    if not verify_totp_code(user.totp_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code.",
        )

    access_token = create_access_token(
        data={"sub": user.email_user, "rol": user.rol_user}
    )
    cookie_samesite = "none" if settings.SECURE_COOKIES else "lax"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite=cookie_samesite,
        secure=settings.SECURE_COOKIES,
        max_age=60 * 60 * 24 * 7,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }

