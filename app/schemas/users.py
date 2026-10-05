from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from typing import Optional


class UserRole(str, Enum):
    Admin = "Admin"
    Seller = "Seller"
    Finance = "Finance"
    Coordinator = "Coordinator"


class UserBase(BaseModel):
    id_user: Optional[int] = None
    name_user: str
    lastname_user: str
    email_user: str
    rol_user: Optional[UserRole] = UserRole.Seller
    created_at: Optional[datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True


class UserCreate(UserBase):
    password_user: str


class UserUpdate(BaseModel):
    name_user: Optional[str] = None
    lastname_user: Optional[str] = None
    email_user: Optional[str] = None
    password_user: Optional[str] = None
    rol_user: Optional[UserRole] = None


class UserDelete(BaseModel):
    id_user: int


class UserResponse(UserBase):
    pass


class UserLogin(BaseModel):
    email_user: str
    password_user: str


class UserRegisterResponse(BaseModel):
    message: str
    user: UserResponse


class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

    class Config:
        from_attributes = True


class UserLoginResponse2FA(BaseModel):
    status: str
    email: str
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True


class TotpRequest(BaseModel):
    code: str
