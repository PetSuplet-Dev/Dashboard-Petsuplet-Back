import logging
from typing import List, Union, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.schemas.users import (
    UserCreate,
    UserUpdate,
    UserDeleteRequest,
    UserResponse,
    UserLogin,
    UserRegisterResponse,
    UserLoginResponse,
    UserLoginResponse2FA,
)
from app.models.users import Users, UserDeletionLog
from app.core.security import get_password_hash, verify_password, create_access_token, verify_totp_code
from app.api.dependencies import get_current_user
from app.config import settings

logger = logging.getLogger("users")
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
        return db.query(Users).order_by(Users.id_user.asc()).offset(offset).limit(limit).all()
    except Exception as e:
        db.rollback()
        logger.error("Error al obtener usuarios: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor. Por favor intente más tarde.")

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
        logger.error("Error al obtener usuario por email: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor. Por favor intente más tarde.")

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
        resolved_nickname = user_in.nickname or user_in.nickname_user
        resolved_phone = user_in.phone or user_in.phone_user

        user_obj = Users(
            name_user=user_in.name_user,
            lastname_user=user_in.lastname_user,
            email_user=user_in.email_user,
            password_user=hashed_password,
            rol_user=user_in.rol_user,
            nickname=resolved_nickname.strip() if resolved_nickname else None,
            phone=resolved_phone.strip() if resolved_phone else None,
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
        logger.error("Error al registrar usuario: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor. Por favor intente más tarde.")

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
                cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
                response.set_cookie(
                    key="access_token",
                    value=access_token,
                    httponly=True,
                    samesite=cookie_samesite,
                    secure=settings.SECURE_COOKIES,
                    max_age=cookie_max_age,
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
        cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            samesite=cookie_samesite,
            secure=settings.SECURE_COOKIES,
            max_age=cookie_max_age,
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
        logger.error("Error en login de usuario: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor al procesar el inicio de sesión.")

@router.post("/refresh", response_model=UserLoginResponse)
def refresh_token(
    response: Response,
    current_user: Users = Depends(get_current_user),
):
    """
    Renueva el token JWT y la cookie HttpOnly del usuario autenticado, extendiendo la sesión activa.
    """
    access_token = create_access_token(
        data={
            "sub": current_user.email_user,
            "rol": current_user.rol_user,
        }
    )
    cookie_samesite = "none" if settings.SECURE_COOKIES else "lax"
    cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite=cookie_samesite,
        secure=settings.SECURE_COOKIES,
        max_age=cookie_max_age,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": current_user,
    }

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
        logger.error("Error al obtener usuario por id: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor. Por favor intente más tarde.")

@router.put("/{id_user}", response_model=UserResponse)
def update_user(
    id_user: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Actualiza la información del perfil de un usuario existente
    """
    try:
        user = db.query(Users).filter(Users.id_user == id_user).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        if user_in.email_user and user_in.email_user != user.email_user:
            existing = db.query(Users).filter(Users.email_user == user_in.email_user).first()
            if existing:
                raise HTTPException(status_code=400, detail="El correo ya se encuentra registrado por otro usuario")
            user.email_user = user_in.email_user

        if user_in.name_user is not None:
            user.name_user = user_in.name_user
        if user_in.lastname_user is not None:
            user.lastname_user = user_in.lastname_user
        if user_in.rol_user is not None:
            user.rol_user = user_in.rol_user
        if user_in.password_user and user_in.password_user.strip():
            user.password_user = get_password_hash(user_in.password_user.strip())

        # Nickname / pronombre
        resolved_nickname = user_in.nickname if user_in.nickname is not None else user_in.nickname_user
        if resolved_nickname is not None:
            user.nickname = resolved_nickname.strip() if resolved_nickname else None

        # Phone / número de contacto
        resolved_phone = user_in.phone if user_in.phone is not None else user_in.phone_user
        if resolved_phone is not None:
            user.phone = resolved_phone.strip() if resolved_phone else None

        db.commit()
        db.refresh(user)
        return user
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Error al actualizar usuario: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor al actualizar el usuario.")

@router.delete("/{id_user}")
def delete_user(
    id_user: int,
    payload: Optional[UserDeleteRequest] = None,
    reason: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Elimina permanentemente el perfil de un usuario de la base de datos,
    registra el comentario/motivo de la eliminación en la tabla de auditoría,
    y reordena los ID internos para que sean correlativos (1..N).
    """
    try:
        if current_user.id_user == id_user:
            raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta en sesión activa")

        user = db.query(Users).filter(Users.id_user == id_user).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        # Motivo o comentario de eliminación
        resolved_reason = None
        if payload and payload.reason and payload.reason.strip():
            resolved_reason = payload.reason.strip()
        elif reason and reason.strip():
            resolved_reason = reason.strip()
        else:
            resolved_reason = "Eliminación administrativa sin comentario específico"

        # 1. Registrar auditoría de eliminación con comentario
        deletion_log = UserDeletionLog(
            original_id_user=user.id_user,
            name_user=user.name_user,
            lastname_user=user.lastname_user,
            email_user=user.email_user,
            rol_user=user.rol_user,
            nickname=user.nickname,
            phone=user.phone,
            deleted_by=current_user.email_user,
            reason=resolved_reason,
        )
        db.add(deletion_log)
        db.flush()

        # 2. Eliminar el usuario permanentemente
        db.delete(user)
        db.flush()

        # 3. Actualizar los IDs internos de la BD para que sean contiguos (1, 2, 3...)
        # Paso 3a: Negar los IDs actuales para evitar violaciones de clave primaria
        db.execute(text("UPDATE users SET id_user = -id_user WHERE id_user > 0"))
        db.flush()

        # Paso 3b: Reasignar IDs contiguos según el orden original
        db.execute(text("""
            WITH numbered AS (
                SELECT id_user, ROW_NUMBER() OVER (ORDER BY id_user DESC) as new_id
                FROM users
            )
            UPDATE users u
            SET id_user = numbered.new_id
            FROM numbered
            WHERE u.id_user = numbered.id_user
        """))
        db.flush()

        # Paso 3c: Sincronizar la secuencia de PostgreSQL para el siguiente ID autoincremental
        db.execute(text("""
            SELECT setval(
                pg_get_serial_sequence('users', 'id_user'),
                COALESCE((SELECT MAX(id_user) FROM users), 1),
                (SELECT COUNT(*) > 0 FROM users)
            )
        """))

        db.commit()
        return {
            "message": "Usuario eliminado correctamente y secuencia de IDs actualizada",
            "id_user": id_user,
            "reason": resolved_reason,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Error al eliminar usuario: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor al eliminar el usuario.")
