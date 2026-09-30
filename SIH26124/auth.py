import base64
import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(prefix="/api/auth", tags=["officers"])
HASH_ROUNDS = 310_000


class Credentials(BaseModel):
    email: str
    password: str
    name: str | None = None
    department: str | None = None
    registration_code: str | None = None


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ROUNDS)
    return f"{base64.b64encode(salt).decode()}:{base64.b64encode(digest).decode()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        salt_text, digest_text = encoded.split(":", 1)
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ROUNDS)
    return hmac.compare_digest(actual, expected)


def require_officer(request: Request) -> int:
    officer_id = request.session.get("officer_id")
    if officer_id is None:
        raise HTTPException(status_code=401, detail="Officer login required")
    return officer_id


@router.post("/signup", status_code=201)
def signup(data: Credentials, db: Session = Depends(get_db)):
    name = (data.name or "").strip()
    email = data.email.strip().lower()
    registration_code = os.environ.get("URBANEYE_REGISTRATION_CODE")
    if registration_code and not hmac.compare_digest(data.registration_code or "", registration_code):
        raise HTTPException(status_code=403, detail="Invalid registration code")
    if len(name) < 2 or "@" not in email or len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Enter a name, valid email, and password of at least 8 characters")
    if db.query(models.Officer).filter_by(email=email).first():
        raise HTTPException(status_code=409, detail="An officer account already exists for this email")
    officer = models.Officer(
        full_name=name,
        email=email,
        department=(data.department or "Transport Authority").strip(),
        password_hash=_hash_password(data.password),
    )
    db.add(officer)
    db.commit()
    db.refresh(officer)
    return {"id": officer.id, "name": officer.full_name, "email": officer.email}


@router.post("/login")
def login(data: Credentials, request: Request, db: Session = Depends(get_db)):
    officer = db.query(models.Officer).filter_by(email=data.email.strip().lower()).first()
    if not officer or not _verify_password(data.password, officer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    request.session.clear()
    request.session["officer_id"] = officer.id
    return {"name": officer.full_name, "email": officer.email}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "signed out"}


@router.get("/me")
def me(officer_id: int = Depends(require_officer), db: Session = Depends(get_db)):
    officer = db.query(models.Officer).filter_by(id=officer_id).first()
    if not officer:
        raise HTTPException(status_code=401, detail="Officer account no longer exists")
    return {"name": officer.full_name, "email": officer.email, "department": officer.department}