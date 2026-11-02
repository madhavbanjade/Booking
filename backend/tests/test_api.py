from datetime import date, timedelta

from app.models import Service, User
from app.security import create_token
from tests.conftest import login, make_user

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def add_service(db, title="Roof Repair", active=True):
    service = Service(
        title=title,
        description="Full roof repair and waterproofing.",
        is_active=active,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


def booking_payload(service_id, **overrides):
    payload = {
        "service_id": service_id,
        "preferred_date": TOMORROW,
        "preferred_time": "10:30:00",
        "message": "Please call before visiting",
    }
    payload.update(overrides)
    return payload


# ---------- Health ----------
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/db").json() == {"database": "connected"}


# ---------- Register, verify, login ----------
def test_register_sends_verification_email(client, sent_emails):
    response = client.post(
        "/auth/register",
        json={"name": "Ram", "email": "Ram@Example.com", "password": "password123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ram@example.com"  # lowercased
    assert body["is_email_verified"] is False
    assert body["role"] == "customer"
    assert "password" not in body and "password_hash" not in body
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "ram@example.com"
    assert "verify-email?token=" in sent_emails[0]["body"]


def test_register_duplicate_email(client):
    data = {"name": "Ram", "email": "ram@example.com", "password": "password123"}
    assert client.post("/auth/register", json=data).status_code == 201
    data["email"] = "RAM@example.com"
    assert client.post("/auth/register", json=data).status_code == 409


def test_register_validation(client):
    response = client.post(
        "/auth/register", json={"name": "R", "email": "bad", "password": "123"}
    )
    assert response.status_code == 422


def test_verify_email_flow(client, db):
    user = make_user(db, "sita@example.com", verified=False)
    token = create_token(user.id, "verify_email", 60)
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    db.refresh(user)
    assert user.is_email_verified is True


def test_verify_email_rejects_wrong_token_purpose(client, db):
    user = make_user(db, "sita@example.com", verified=False)
    token = create_token(user.id, "access", 60)  # wrong purpose
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": "garbage"}).status_code == 400


def test_login_me_logout(client, db):
    make_user(db, "ram@example.com")
    assert client.get("/auth/me").status_code == 401

    bad = client.post(
        "/auth/login", json={"email": "ram@example.com", "password": "wrongpass1"}
    )
    assert bad.status_code == 401

    response = login(client, "ram@example.com")
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie

    assert client.get("/auth/me").json()["email"] == "ram@example.com"
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_password_reset_flow(client, db, sent_emails):
    make_user(db, "ram@example.com")
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert unknown.status_code == 200
    assert sent_emails == []  # no email for unknown accounts, same response

    known = client.post("/auth/forgot-password", json={"email": "ram@example.com"})
    assert known.status_code == 200
    assert len(sent_emails) == 1
    token = sent_emails[0]["body"].split("token=")[1].split('"')[0]

    reset = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "newpassword99"}
    )
    assert reset.status_code == 200
    login(client, "ram@example.com", "newpassword99")

    # The same link cannot be used twice (password fingerprint changed).
    again = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "another12345"}
    )
    assert again.status_code == 400


# ---------- Services ----------
def test_public_services_only_shows_active(client, db):
    add_service(db, "Roof Repair", active=True)
    add_service(db, "Hidden Service", active=False)
    titles = [s["title"] for s in client.get("/services").json()]
    assert titles == ["Roof Repair"]


def test_hidden_service_not_found_publicly(client, db):
    hidden = add_service(db, "Hidden", active=False)
    assert client.get(f"/services/{hidden.id}").status_code == 404


def test_admin_service_management(admin_client):
    create = admin_client.post(
        "/admin/services",
        json={"title": "Bathroom Renovation", "description": "Complete renovation."},
    )
    assert create.status_code == 201
    service_id = create.json()["id"]
    assert create.json()["is_active"] is True

    patch = admin_client.patch(
        f"/admin/services/{service_id}", json={"title": "Bathroom Remodel"}
    )
    assert patch.json()["title"] == "Bathroom Remodel"

    # Hide it: disappears from the public list but stays in the admin list.
    admin_client.patch(f"/admin/services/{service_id}", json={"is_active": False})
    assert admin_client.get("/services").json() == []
    assert len(admin_client.get("/admin/services").json()) == 1

    # A null title must not wipe the required column.
    admin_client.patch(f"/admin/services/{service_id}", json={"title": None})
    assert admin_client.get("/admin/services").json()[0]["title"] == "Bathroom Remodel"

    # The image can be cleared.
    admin_client.patch(f"/admin/services/{service_id}", json={"image_url": "https://x/y.jpg"})
    cleared = admin_client.patch(f"/admin/services/{service_id}", json={"image_url": None})
    assert cleared.json()["image_url"] is None


def test_service_management_requires_admin(customer_client, client):
    payload = {"title": "Sneaky", "description": "Customers cannot do this."}
    assert customer_client.post("/admin/services", json=payload).status_code == 403
    assert customer_client.get("/admin/services").status_code == 403
    client.post("/auth/logout")
    assert client.post("/admin/services", json=payload).status_code == 401


def test_upload_requires_admin_and_config(customer_client, admin_client):
    # admin_client and customer_client share one test client; log in as each in turn.
    login(admin_client, "ram@example.com")
    files = {"file": ("a.png", b"123", "image/png")}
    assert admin_client.post("/admin/uploads", files=files).status_code == 403
    admin_client.post("/auth/logout")
    login(admin_client, "admin@example.com")
    # Cloudinary is not configured in tests -> 503, not a crash.
    assert admin_client.post("/admin/uploads", files=files).status_code == 503


# ---------- Appointments ----------
def test_booking_requires_login_and_verified_email(client, db):
    service = add_service(db)
    payload = booking_payload(service.id)
    assert client.post("/appointments", json=payload).status_code == 401

    make_user(db, "new@example.com", verified=False)
    login(client, "new@example.com")
    assert client.post("/appointments", json=payload).status_code == 403


def test_customer_books_and_sees_own_bookings(customer_client, db, sent_emails):
    service = add_service(db)
    response = customer_client.post("/appointments", json=booking_payload(service.id))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["payment_status"] == "unpaid"
    assert body["service"]["title"] == "Roof Repair"

    recipients = sorted(email["to"] for email in sent_emails)
    assert recipients == ["owner@example.com", "ram@example.com"]

    mine = customer_client.get("/appointments/mine").json()
    assert len(mine) == 1 and mine[0]["id"] == body["id"]


def test_booking_validation(customer_client, db):
    service = add_service(db)
    inactive = add_service(db, "Hidden", active=False)
    past = (date.today() - timedelta(days=1)).isoformat()
    assert (
        customer_client.post(
            "/appointments", json=booking_payload(service.id, preferred_date=past)
        ).status_code
        == 422
    )
    assert customer_client.post("/appointments", json=booking_payload(9999)).status_code == 404
    assert (
        customer_client.post("/appointments", json=booking_payload(inactive.id)).status_code
        == 404
    )


def test_pending_limit(customer_client, db):
    service = add_service(db)
    for _ in range(5):
        assert (
            customer_client.post("/appointments", json=booking_payload(service.id)).status_code
            == 201
        )
    sixth = customer_client.post("/appointments", json=booking_payload(service.id))
    assert sixth.status_code == 400


def test_customers_only_see_their_own_bookings(client, db):
    service = add_service(db)
    make_user(db, "a@example.com")
    make_user(db, "b@example.com")
    login(client, "a@example.com")
    client.post("/appointments", json=booking_payload(service.id))
    client.post("/auth/logout")
    login(client, "b@example.com")
    assert client.get("/appointments/mine").json() == []


def test_admin_review_flow(client, db, sent_emails):
    service = add_service(db)
    make_user(db, "admin@example.com", role="admin")
    make_user(db, "ram@example.com")

    login(client, "ram@example.com")
    booking = client.post("/appointments", json=booking_payload(service.id)).json()
    assert client.get("/admin/appointments").status_code == 403
    client.post("/auth/logout")
    sent_emails.clear()

    login(client, "admin@example.com")
    page = client.get("/admin/appointments").json()
    assert page["total"] == 1
    assert page["items"][0]["user"]["email"] == "ram@example.com"

    approve = client.patch(
        f"/admin/appointments/{booking['id']}/status",
        json={"status": "approved", "admin_note": "See you then"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    assert approve.json()["admin_note"] == "See you then"
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "ram@example.com"
    assert "approved" in sent_emails[0]["subject"]

    # Approving again does not email the customer a second time.
    client.patch(
        f"/admin/appointments/{booking['id']}/status", json={"status": "approved"}
    )
    assert len(sent_emails) == 1

    # Completing does not email either.
    client.patch(
        f"/admin/appointments/{booking['id']}/status", json={"status": "completed"}
    )
    assert len(sent_emails) == 1

    paid = client.patch(
        f"/admin/appointments/{booking['id']}/payment", json={"payment_status": "paid"}
    )
    assert paid.json()["payment_status"] == "paid"


def test_admin_filters_search_and_stats(client, db):
    roof = add_service(db, "Roof Repair")
    paint = add_service(db, "Painting")
    make_user(db, "admin@example.com", role="admin")
    make_user(db, "ram@example.com")
    make_user(db, "sita@example.com")

    login(client, "ram@example.com")
    client.post("/appointments", json=booking_payload(roof.id))
    client.post("/appointments", json=booking_payload(paint.id))
    client.post("/auth/logout")
    login(client, "sita@example.com")
    client.post("/appointments", json=booking_payload(roof.id))
    client.post("/auth/logout")

    login(client, "admin@example.com")
    all_items = client.get("/admin/appointments").json()
    assert all_items["total"] == 3

    first_id = all_items["items"][0]["id"]
    client.patch(f"/admin/appointments/{first_id}/status", json={"status": "rejected"})

    assert client.get("/admin/appointments?status=rejected").json()["total"] == 1
    assert client.get("/admin/appointments?status=pending").json()["total"] == 2
    assert client.get(f"/admin/appointments?service_id={paint.id}").json()["total"] == 1
    assert client.get("/admin/appointments?search=sita").json()["total"] == 1
    assert client.get("/admin/appointments?search=RAM@example").json()["total"] == 2

    paged = client.get("/admin/appointments?page=2&page_size=2").json()
    assert paged["total"] == 3 and len(paged["items"]) == 1

    stats = client.get("/admin/appointments/stats").json()
    assert stats == {
        "total": 3,
        "pending": 2,
        "approved": 0,
        "rejected": 1,
        "completed": 0,
    }


def test_admin_get_single_appointment_and_404(admin_client):
    assert admin_client.get("/admin/appointments/999").status_code == 404
