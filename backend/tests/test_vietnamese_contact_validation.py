import pytest
from pydantic import ValidationError

from app.api.v1.canonical_extensions import ManagedUserCreate, ManagedUserUpdate
from app.core.enums import UserRole, UserStatus
from app.schemas.user import AdminUserCreate, UserCreate, UserSelfUpdate


def _managed_create(**overrides):
    payload = {
        "username": "contact.validation",
        "full_name": "Nguyễn Văn A",
        "email": "contact.validation@gmail.com",
        "phone_number": "0912345678",
        "address": "Hà Nội",
        "role_id": None,
        "password": "RequiredInfo@123",
        "confirm_password": "RequiredInfo@123",
        "must_change_password": True,
    }
    payload.update(overrides)
    return ManagedUserCreate.model_validate(payload)


@pytest.mark.parametrize(
    ("phone_number", "expected"),
    [
        ("0912345678", "0912345678"),
        ("0321234567", "0321234567"),
        ("0581234567", "0581234567"),
        ("0701234567", "0701234567"),
        ("0811234567", "0811234567"),
        ("+84912345678", "0912345678"),
        ("+84321234567", "0321234567"),
    ],
)
def test_managed_user_create_accepts_and_normalizes_vietnamese_mobile_numbers(
    phone_number: str,
    expected: str,
) -> None:
    assert _managed_create(phone_number=phone_number).phone_number == expected


@pytest.mark.parametrize(
    "phone_number",
    [
        "0612345678",
        "0212345678",
        "091234567",
        "09123456789",
        "+12345678901",
        "09123abc78",
        "0912 345 678",
    ],
)
def test_managed_user_create_rejects_non_vietnamese_mobile_numbers(
    phone_number: str,
) -> None:
    with pytest.raises(ValidationError):
        _managed_create(phone_number=phone_number)


def test_managed_user_create_requires_gmail_and_normalizes_case() -> None:
    row = _managed_create(email="  Contact.Validation@GMAIL.COM  ")
    assert str(row.email) == "contact.validation@gmail.com"

    with pytest.raises(ValidationError):
        _managed_create(email="contact.validation@yahoo.com")


@pytest.mark.parametrize(
    "schema,payload",
    [
        (ManagedUserUpdate, {"phone_number": "+84912345678", "email": "Update.User@GMAIL.COM"}),
        (UserSelfUpdate, {"phone_number": "+84912345678", "email": "Self.User@GMAIL.COM"}),
    ],
)
def test_update_schemas_share_vietnamese_phone_and_gmail_rules(schema, payload) -> None:
    row = schema.model_validate(payload)
    assert row.phone_number == "0912345678"
    assert str(row.email).endswith("@gmail.com")

    with pytest.raises(ValidationError):
        schema.model_validate({"phone_number": "0612345678"})
    with pytest.raises(ValidationError):
        schema.model_validate({"email": "user@example.com"})


def test_legacy_user_create_and_admin_create_share_contact_rules() -> None:
    user = UserCreate.model_validate(
        {
            "username": "legacy.user",
            "full_name": "Legacy User",
            "email": "legacy.user@gmail.com",
            "phone_number": "+84912345678",
            "address": "Hà Nội",
            "temporary_password": "RequiredInfo@123",
            "role_id": None,
        }
    )
    assert user.phone_number == "0912345678"

    admin = AdminUserCreate.model_validate(
        {
            "username": "admin.user",
            "full_name": "Admin User",
            "email": "admin.user@gmail.com",
            "phone_number": "0912345678",
            "address": "Hà Nội",
            "system_role": UserRole.ADMIN,
            "status": UserStatus.ACTIVE,
            "password": "RequiredInfo@123",
            "confirm_password": "RequiredInfo@123",
            "must_change_password": False,
        }
    )
    assert str(admin.email) == "admin.user@gmail.com"

    with pytest.raises(ValidationError):
        UserCreate.model_validate(
            {
                "username": "legacy.invalid",
                "full_name": "Legacy Invalid",
                "email": "legacy.invalid@example.com",
                "phone_number": "0912345678",
                "address": "Hà Nội",
                "temporary_password": "RequiredInfo@123",
            }
        )
