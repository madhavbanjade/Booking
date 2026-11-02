from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user, get_verified_user, require_admin
from app.emailer import (
    send_admin_new_booking,
    send_booking_received,
    send_status_update,
)
from app.models import Appointment, AppointmentStatus, PaymentStatus, Service, User
from app.schemas import (
    AppointmentAdminOut,
    AppointmentAdminPage,
    AppointmentCreate,
    AppointmentOut,
    AppointmentPaymentUpdate,
    AppointmentStats,
    AppointmentStatusUpdate,
)

router = APIRouter()

MAX_PENDING_PER_USER = 5


def _get_or_404(db: Session, appointment_id: int) -> Appointment:
    stmt = (
        select(Appointment)
        .options(joinedload(Appointment.service), joinedload(Appointment.user))
        .where(Appointment.id == appointment_id)
    )
    appointment = db.scalar(stmt)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment


# ---------- Customer ----------
@router.post(
    "/appointments",
    response_model=AppointmentOut,
    status_code=201,
    tags=["Appointments"],
)
def create_appointment(
    data: AppointmentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_verified_user),
):
    service = db.get(Service, data.service_id)
    if service is None or not service.is_active:
        raise HTTPException(status_code=404, detail="Service not found")

    pending = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.user_id == user.id,
            Appointment.status == AppointmentStatus.pending,
        )
    )
    if pending >= MAX_PENDING_PER_USER:
        raise HTTPException(
            status_code=400,
            detail="You already have several pending requests. Please wait for a reply.",
        )

    # Copy the values we need for emails before committing (background tasks
    # run after the response and must not touch the database session).
    customer = (user.name, user.email)
    service_title = service.title

    appointment = Appointment(
        user_id=user.id,
        service_id=service.id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
        message=data.message,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    background_tasks.add_task(
        send_booking_received,
        customer[1],
        customer[0],
        service_title,
        data.preferred_date,
        data.preferred_time,
    )
    background_tasks.add_task(
        send_admin_new_booking,
        customer[0],
        customer[1],
        service_title,
        data.preferred_date,
        data.preferred_time,
        data.message,
    )
    return appointment


@router.get(
    "/appointments/mine", response_model=list[AppointmentOut], tags=["Appointments"]
)
def my_appointments(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    stmt = (
        select(Appointment)
        .options(joinedload(Appointment.service))
        .where(Appointment.user_id == user.id)
        .order_by(Appointment.created_at.desc(), Appointment.id.desc())
    )
    return db.scalars(stmt).all()


# ---------- Admin ----------
@router.get(
    "/admin/appointments",
    response_model=AppointmentAdminPage,
    tags=["Admin - Appointments"],
)
def admin_list_appointments(
    status: AppointmentStatus | None = None,
    payment_status: PaymentStatus | None = None,
    service_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    stmt = select(Appointment).join(Appointment.user)
    if status:
        stmt = stmt.where(Appointment.status == status)
    if payment_status:
        stmt = stmt.where(Appointment.payment_status == payment_status)
    if service_id:
        stmt = stmt.where(Appointment.service_id == service_id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(
        stmt.options(joinedload(Appointment.service), joinedload(Appointment.user))
        .order_by(Appointment.created_at.desc(), Appointment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get(
    "/admin/appointments/stats",
    response_model=AppointmentStats,
    tags=["Admin - Appointments"],
)
def admin_stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.execute(
        select(Appointment.status, func.count()).group_by(Appointment.status)
    ).all()
    counts = {s.value: 0 for s in AppointmentStatus}
    for row_status, number in rows:
        counts[row_status.value] = number
    return {"total": sum(counts.values()), **counts}


@router.get(
    "/admin/appointments/{appointment_id}",
    response_model=AppointmentAdminOut,
    tags=["Admin - Appointments"],
)
def admin_get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return _get_or_404(db, appointment_id)


@router.patch(
    "/admin/appointments/{appointment_id}/status",
    response_model=AppointmentAdminOut,
    tags=["Admin - Appointments"],
)
def admin_update_status(
    appointment_id: int,
    data: AppointmentStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    appointment = _get_or_404(db, appointment_id)
    previous_status = appointment.status

    appointment.status = data.status
    if "admin_note" in data.model_fields_set:
        appointment.admin_note = data.admin_note

    # Copy values for the email before committing.
    customer_email = appointment.user.email
    customer_name = appointment.user.name
    service_title = appointment.service.title

    db.commit()
    db.refresh(appointment)

    decided = data.status in (AppointmentStatus.approved, AppointmentStatus.rejected)
    if decided and data.status != previous_status:
        background_tasks.add_task(
            send_status_update,
            customer_email,
            customer_name,
            service_title,
            data.status.value,
            appointment.admin_note,
        )
    return appointment


@router.patch(
    "/admin/appointments/{appointment_id}/payment",
    response_model=AppointmentAdminOut,
    tags=["Admin - Appointments"],
)
def admin_update_payment(
    appointment_id: int,
    data: AppointmentPaymentUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    appointment = _get_or_404(db, appointment_id)
    appointment.payment_status = data.payment_status
    db.commit()
    db.refresh(appointment)
    return appointment
