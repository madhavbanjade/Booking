"""Create the first admin account.

Run from the backend/ folder:  python -m scripts.create_admin
"""

import getpass

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def main() -> None:
    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Password (at least 8 characters): ")

    if len(name) < 2 or "@" not in email:
        raise SystemExit("Please enter a valid name and email.")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("A user with this email already exists.")
        db.add(
            User(
                name=name,
                email=email,
                password_hash=hash_password(password),
                role=UserRole.admin,
                is_email_verified=True,
            )
        )
        db.commit()
    print(f"Admin created: {email}")


if __name__ == "__main__":
    main()
