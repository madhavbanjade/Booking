from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Service, User
from app.schemas import ServiceCreate, ServiceOut, ServiceUpdate

router = APIRouter()


# ---------- Public ----------
@router.get("/services", response_model=list[ServiceOut], tags=["Services"])
def list_services(db: Session = Depends(get_db)):
    stmt = select(Service).where(Service.is_active.is_(True)).order_by(Service.id.desc())
    return db.scalars(stmt).all()


@router.get("/services/{service_id}", response_model=ServiceOut, tags=["Services"])
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    if service is None or not service.is_active:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


# ---------- Admin ----------
@router.get(
    "/admin/services", response_model=list[ServiceOut], tags=["Admin - Services"]
)
def admin_list_services(
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    return db.scalars(select(Service).order_by(Service.id.desc())).all()


@router.post(
    "/admin/services",
    response_model=ServiceOut,
    status_code=201,
    tags=["Admin - Services"],
)
def create_service(
    data: ServiceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    service = Service(**data.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.patch(
    "/admin/services/{service_id}",
    response_model=ServiceOut,
    tags=["Admin - Services"],
)
def update_service(
    service_id: int,
    data: ServiceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field != "image_url":
            continue  # only the image can be cleared; the other columns are required
        setattr(service, field, value)

    db.commit()
    db.refresh(service)
    return service
