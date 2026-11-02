from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import AppointmentStatus, PaymentStatus, UserRole


# ---------- Generic ----------
class MessageOut(BaseModel):
    message: str


class TokenIn(BaseModel):
    token: str


# ---------- Users and auth ----------
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    turnstile_token: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    phone: str | None
    role: UserRole
    is_email_verified: bool


# ---------- Services ----------
class ServiceBase(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=10)
    image_url: str | None = Field(default=None, max_length=500)


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, min_length=10)
    image_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ServiceOut(ServiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool


class UploadOut(BaseModel):
    url: str


# ---------- Appointments ----------
class AppointmentCreate(BaseModel):
    service_id: int
    preferred_date: date
    preferred_time: time
    message: str | None = Field(default=None, max_length=2000)

    @field_validator("preferred_date")
    @classmethod
    def date_not_in_past(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("Preferred date cannot be in the past")
        return value


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus
    admin_note: str | None = Field(default=None, max_length=2000)


class AppointmentPaymentUpdate(BaseModel):
    payment_status: PaymentStatus


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service: ServiceOut
    preferred_date: date
    preferred_time: time
    message: str | None
    status: AppointmentStatus
    admin_note: str | None
    payment_status: PaymentStatus
    created_at: datetime


class AppointmentAdminOut(AppointmentOut):
    user: UserOut


class AppointmentAdminPage(BaseModel):
    items: list[AppointmentAdminOut]
    total: int
    page: int
    page_size: int


class AppointmentStats(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int
    completed: int
