from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:////opt/streamlit-platform/registry/apps.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class App(Base):
    __tablename__ = "apps"

    id       = Column(Integer, primary_key=True)
    name     = Column(String, unique=True, nullable=False)
    port     = Column(Integer, unique=True, nullable=False)
    app_type = Column(String, nullable=False)               # "streamlit" | "dash"
    owner    = Column(String, nullable=False)
    status   = Column(String, default="stopped")            # "running" | "stopped" | "error" | "starting"
    created  = Column(DateTime, default=datetime.utcnow)
    updated  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def list_running_apps(db) -> list[App]:
    return db.query(App).filter(App.status == "running").order_by(App.name).all()


def get_next_port(db, start: int = 8501, end: int = 8600) -> int:
    used = {r[0] for r in db.query(App.port).all()}
    for p in range(start, end):
        if p not in used:
            return p
    raise RuntimeError("No hay puertos disponibles en el rango asignado")
