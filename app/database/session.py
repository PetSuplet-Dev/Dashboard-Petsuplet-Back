from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

# Configurar el motor de base de datos con connection pool y pre-ping para evitar caídas por inactividad
engine_kwargs = {
    "pool_pre_ping": True,
}
if "sqlite" not in settings.DATABASE_URL.lower():
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
    })

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa para todos los modelos ORM
Base = declarative_base()

# Dependencia para obtener la sesión de la base de datos en los endpoints de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
