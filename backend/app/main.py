from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.routers import appointments, auth, services, uploads

# jdyttdufu uyytftuf
app = FastAPI(title="Booking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(services.router)
app.include_router(appointments.router)
app.include_router(uploads.router)


@app.get("/", tags=["Health"])
def read_root():
    return {"message": "Booking API is running"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


@app.get("/health/db", tags=["Health"])
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "connected"}
