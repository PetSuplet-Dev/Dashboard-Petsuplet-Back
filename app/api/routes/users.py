from typing import List, Union, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.schemas.users import UserCreate, UserResponse, UserLogin, UserRegisterResponse, UserLoginResponse, UserLoginResponse2FA
from app.models.users import Users
from app.core.security import get_password_hash, verify_password, create_access_token, verify_totp_code
from app.api.dependencies import get_current_user
from app.config import settings

router = APIRouter()

@router.get("/", response_model=List[UserResponse])
def get_users(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum number of items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Obtiene los usuarios registrados en la base de datos de manera paginada
    """
    try:
        return db.query(Users).offset(offset).limit(limit).all()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: Users = Depends(get_current_user)):
    """
    Obtiene el perfil del usuario autenticado actual mediante su token Bearer
    """
    return current_user

@router.get("/email/{email_user}", response_model=UserResponse)
def get_user_email(
    email_user: str,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Obtiene un usuario registrado por su email
    """
    try:
        user = db.query(Users).filter(Users.email_user == email_user).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return user
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Registra un nuevo usuario, cifrando su contraseña
    """
    try:
        # Verificar si el email ya existe
        existing_user = db.query(Users).filter(Users.email_user == user_in.email_user).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="El correo ya se encuentra registrado")
        
        # Cifrar contraseña y crear objeto de modelo
        hashed_password = get_password_hash(user_in.password_user)
        user_obj = Users(
            name_user=user_in.name_user,
            lastname_user=user_in.lastname_user,
            email_user=user_in.email_user,
            password_user=hashed_password,
            rol_user=user_in.rol_user
        )
        db.add(user_obj)
        db.commit()
        db.refresh(user_obj)
        
        message_text = f"Usuario registrado con éxito. ¡Tu eres {user_obj.rol_user}!"
        return UserRegisterResponse(message=message_text, user=user_obj)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login", response_model=Union[UserLoginResponse, UserLoginResponse2FA])
async def login_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Inicia sesión verificando credenciales del usuario.
    Soporta formato JSON (email_user/password_user) y Form Data de Swagger (username/password).
    """
    try:
        totp_code = None
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            email = form.get("username") or form.get("email_user")
            password = form.get("password") or form.get("password_user")
            totp_code = form.get("client_secret") or form.get("totp_code") or form.get("code")
        else:
            body = await request.json()
            email = body.get("email_user") or body.get("username")
            password = body.get("password_user") or body.get("password")
            totp_code = body.get("totp_code") or body.get("client_secret") or body.get("code")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email y contraseña son requeridos")

        def _get_user():
            return db.query(Users).filter(Users.email_user == email).first()

        user = await run_in_threadpool(_get_user)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no registrado")
        
        if not verify_password(password, user.password_user):
            raise HTTPException(status_code=400, detail="Contraseña incorrecta")

        if user.is_totp_enabled or user.totp_secret:
            if not user.is_totp_enabled and user.totp_secret:
                user.is_totp_enabled = True
                await run_in_threadpool(db.commit)

            # If TOTP code was supplied (e.g. Swagger Authorize client_secret or 1-step login)
            if totp_code and user.totp_secret and verify_totp_code(user.totp_secret, str(totp_code).strip()):
                access_token = create_access_token(
                    data={
                        "sub": user.email_user,
                        "rol": user.rol_user
                    }
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
                    "user": user
                }

            return {
                "status": "2fa_required",
                "email": user.email_user,
                "user": user,
            }

        access_token = create_access_token(
            data={
                "sub": user.email_user,
                "rol": user.rol_user
            }
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
            "user": user
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/logout")
def logout_user(response: Response):
    """
    Cierra la sesión del usuario eliminando la cookie HttpOnly access_token
    """
    cookie_samesite = "none" if settings.SECURE_COOKIES else "lax"
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite=cookie_samesite,
        secure=settings.SECURE_COOKIES,
    )
    return {"message": "Sesión cerrada correctamente"}

@router.get("/{id_user}", response_model=UserResponse)
def get_user(
    id_user: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Obtiene un usuario registrado por su ID numérico
    """
    try:
        user = db.query(Users).filter(Users.id_user == id_user).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return user
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))