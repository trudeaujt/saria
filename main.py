from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel, AnyHttpUrl
from sqlalchemy import create_engine, Column, String, Integer, DateTime, func, select
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
from enum import Enum
import logging
from pathlib import Path
from logging.config import fileConfig
import random
import string

config_path = Path(__file__).parent / "logging.ini"
fileConfig(config_path)
logger = logging.getLogger(__name__)

class Platform(str, Enum):
   DESKTOP = "desktop"
   MOBILE = "mobile"
   TABLET = "tablet"
   UNKNOWN = "unknown"

app = FastAPI()

# Database Configuration
SQLALCHEMY_DATABASE_URL = "postgresql://user:password@localhost/saria"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class LinkMapping(Base):
    __tablename__ = "link_mappings"
    short_url: Column[str] = Column(String, primary_key=True, index=True)
    long_url: Column[str] = Column(String, index=True)
    created_at: Column[datetime] = Column(DateTime, default=datetime.utcnow)
    last_accessed_at: Column[datetime] = Column(DateTime, default=datetime.utcnow)
    access_count: Column[int] = Column(Integer, default=0)

class ClickMetadata(Base):
    __tablename__ = "click_metadata"
    id: Column[int] = Column(Integer, primary_key=True, index=True)
    short_url: Column[str] = Column(String, index=True)
    timestamp: Column[datetime] = Column(DateTime, default=datetime.utcnow)
    region: Column[str] | None = Column(String)
    browser: Column[str] | None = Column(String)
    platform: Column[str] = Column(String)

Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_short_url(db: Session) -> str:
    characters = string.ascii_letters + string.digits
    while True:
        short_url = ''.join(random.choice(characters) for _ in range(5))
        if not db.query(LinkMapping).filter(LinkMapping.short_url == short_url).first():
            return short_url

@app.post("/shorten", response_model=LinkMapping)
def shorten_url(long_url: AnyHttpUrl, db: Session = Depends(get_db)) -> LinkMapping:
    short_url = generate_short_url(db)
    url_mapping = LinkMapping(short_url=short_url, long_url=str(long_url))
    db.add(url_mapping)
    db.commit()
    db.refresh(url_mapping)
    return url_mapping

@app.get("/{short_url}")
def redirect_url(short_url: str, request: Request, db: Session = Depends(get_db)):
    url_mapping = db.query(LinkMapping).filter(LinkMapping.short_url == short_url).first()
    if not url_mapping:
        raise HTTPException(status_code=404, detail="URL not found.")

    # Update click tracking and access count
    db.query(LinkMapping).filter(LinkMapping.short_url == short_url).update({
        LinkMapping.access_count: LinkMapping.access_count + 1,
        LinkMapping.last_accessed_at: datetime.utcnow()
    })

    click_metadata = ClickMetadata(
        short_url = short_url,
        region=request.client.host if request.client else "Unknown",
        browser=request.headers.get("User-Agent"),
        platform=request.headers.get("Sec-Ch-Ua-Platform")
    )
    db.add(click_metadata)
    db.commit()

    return {"redirect_url": url_mapping.long_url}

@app.get("/mappings", response_model=dict[str, LinkMapping])
def get_url_mappings(db: Session = Depends(get_db)) -> dict[str, LinkMapping]:
    url_mappings = db.query(LinkMapping).all()
    return {mapping.short_url: mapping for mapping in url_mappings}

@app.get("healthz")
def health_check():
    return {"status": "ok"}

@app.get("/readyz")
def readiness_check(db: Session = Depends(get_db)):
    try:
        result = db.scalar(select(1))
        if result == 1:
            return {"status": "ok"}
        else:
            raise HTTPException(status_code=500, detail="Database not ready")
    except:
        raise HTTPException(status_code=500, detail="Database not ready")

logger.info("Application started")
