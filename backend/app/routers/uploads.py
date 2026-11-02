import logging
import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import settings
from app.deps import require_admin
from app.models import User
from app.schemas import UploadOut

router = APIRouter()
logger = logging.getLogger('uvicorn.error')

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/admin/uploads", response_model=UploadOut, tags=["Admin - Uploads"])
def upload_image(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
):
    if not (
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
    ):
        raise HTTPException(status_code=503, detail="Image uploads are not configured")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or WebP images")

    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    try:
        result = cloudinary.uploader.upload(
            data, folder="booking/services", resource_type="image"
        )
    except CloudinaryError as exc:
        logger.error("Cloudinary upload failed: %s", exc)
        raise HTTPException(status_code=502, detail="Image upload failed") from exc

    return {"url": result["secure_url"]}
