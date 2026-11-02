from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.captcha import verify_turnstile
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.emailer import send_password_reset_email, send_verification_email
from app.models import User
from app.schemas import (
    ForgotPasswordIn,
    MessageOut,
    ResetPasswordIn,
    TokenIn,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.security import (
    ACCESS_COOKIE,
    create_token,
    decode_token,
    hash_password,
    password_fingerprint,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

VERIFY_EMAIL_MINUTES = 60 * 24
RESET_PASSWORD_MINUTES = 30


def _cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    data: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not verify_turnstile(data.turnstile_token):
        raise HTTPException(status_code=400, detail="Captcha verification failed")

    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="This email is already registered")

    user = User(
        name=data.name.strip(),
        email=email,
        phone=data.phone,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This email is already registered")
    db.refresh(user)

    token = create_token(user.id, "verify_email", VERIFY_EMAIL_MINUTES)
    background_tasks.add_task(send_verification_email, user.email, user.name, token)
    return user


@router.post("/login", response_model=UserOut)
def login(data: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user.id, "access", settings.access_token_expire_minutes)
    response.set_cookie(
        ACCESS_COOKIE,
        token,
        max_age=settings.access_token_expire_minutes * 60,
        **_cookie_options(),
    )
    return user


@router.post("/logout", response_model=MessageOut)
def logout(response: Response):
    response.delete_cookie(ACCESS_COOKIE, **_cookie_options())
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/verify-email", response_model=MessageOut)
def verify_email(data: TokenIn, db: Session = Depends(get_db)):
    payload = decode_token(data.token, "verify_email")
    user = db.get(User, int(payload["sub"])) if payload else None
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired link")
    user.is_email_verified = True
    db.commit()
    return {"message": "Email verified"}


@router.post("/resend-verification", response_model=MessageOut)
def resend_verification(
    background_tasks: BackgroundTasks, user: User = Depends(get_current_user)
):
    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified")
    token = create_token(user.id, "verify_email", VERIFY_EMAIL_MINUTES)
    background_tasks.add_task(send_verification_email, user.email, user.name, token)
    return {"message": "Verification email sent"}


@router.post("/forgot-password", response_model=MessageOut)
def forgot_password(
    data: ForgotPasswordIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is not None:
        token = create_token(
            user.id,
            "reset_password",
            RESET_PASSWORD_MINUTES,
            fingerprint=password_fingerprint(user.password_hash),
        )
        background_tasks.add_task(
            send_password_reset_email, user.email, user.name, token
        )
    # Same answer whether or not the email exists, so nobody can probe for accounts.
    return {"message": "If that email is registered, a reset link has been sent"}


@router.post("/reset-password", response_model=MessageOut)
def reset_password(data: ResetPasswordIn, db: Session = Depends(get_db)):
    payload = decode_token(data.token, "reset_password")
    user = db.get(User, int(payload["sub"])) if payload else None
    if (
        user is None
        or payload.get("fp") != password_fingerprint(user.password_hash)
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired link")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password updated. You can log in now."}
