import uuid
from sqlalchemy import Column, Integer, String, DateTime, Text, func, Boolean
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
    nickname = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)

    @property
    def nickname_user(self):
        return self.nickname

    @nickname_user.setter
    def nickname_user(self, value):
        self.nickname = value

    @property
    def phone_user(self):
        return self.phone

    @phone_user.setter
    def phone_user(self, value):
        self.phone = value

    @property
    def id(self) -> uuid.UUID:
        return uuid.UUID(int=self.id_user)

    def __repr__(self):
        return f"User(id_user={self.id_user}, name_user={self.name_user}, lastname_user={self.lastname_user}, nickname={self.nickname}, phone={self.phone}, email_user={self.email_user}, rol_user={self.rol_user}, created_at={self.created_at})"


class UserDeletionLog(Base):
    __tablename__ = 'user_deletion_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    original_id_user = Column(Integer, nullable=False)
    name_user = Column(String(100), nullable=False)
    lastname_user = Column(String(150), nullable=False)
    email_user = Column(String(150), nullable=False)
    rol_user = Column(String(50), nullable=False)
    nickname = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    deleted_by = Column(String(150), nullable=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    def __repr__(self):
        return f"UserDeletionLog(id={self.id}, original_id_user={self.original_id_user}, email_user={self.email_user}, reason={self.reason})"
