import uuid
from sqlalchemy import Column, Integer, String, DateTime, func, Boolean
from app.database.session import Base

class Users(Base):
    __tablename__ = 'users'
    
    id_user = Column(Integer, primary_key=True, autoincrement=True)
    name_user = Column(String(100), nullable=False)
    lastname_user = Column(String(150), nullable=False)
    email_user = Column(String(150), nullable=False, unique=True)
    password_user = Column(String(150), nullable=False)
    rol_user = Column(String(50), nullable=False, default='Seller')
    created_at = Column(DateTime, nullable=False, default=func.now())
    totp_secret = Column(String, nullable=True)
    is_totp_enabled = Column(Boolean, default=False)

    @property
    def id(self) -> uuid.UUID:
        return uuid.UUID(int=self.id_user)

    def __repr__(self):
        return f"User(id_user={self.id_user}, name_user={self.name_user}, lastname_user={self.lastname_user}, email_user={self.email_user}, rol_user={self.rol_user}, created_at={self.created_at})"