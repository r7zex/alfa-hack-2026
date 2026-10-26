"""Validated API contracts for authentication and the current business profile."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models.auth import UserRole


class AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("email", check_fields=False)
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if len(value) > 255:
            raise ValueError("Email is too long")
        return value.lower()


class LoginRequest(AuthInput):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    type: Literal["ip", "llc"] | None = None
    inn: str | None = Field(default=None, pattern=r"^[0-9]{10}([0-9]{2})?$")


class RegisterBase(AuthInput):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Укажите имя или название бизнеса")
        return value

    @field_validator("inn", check_fields=False)
    @classmethod
    def validate_inn(cls, value: str) -> str:
        digits = list(map(int, value))

        def check(weights):
            return sum(w * n for w, n in zip(weights, digits)) % 11 % 10

        valid = (
            check([2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]
            if len(value) == 10
            else (
                check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[10]
                and check([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[11]
            )
        )
        if not any(digits) or not valid:
            raise ValueError("Контрольные цифры ИНН не совпадают")
        return value


class IPRegisterRequest(RegisterBase):
    type: Literal["ip"]
    inn: str = Field(pattern=r"^[0-9]{12}$")


class LegalRegisterRequest(RegisterBase):
    type: Literal["llc"]
    inn: str = Field(pattern=r"^[0-9]{10}$")


RegisterRequest = Annotated[
    IPRegisterRequest | LegalRegisterRequest, Field(discriminator="type")
]


class BusinessResponse(BaseModel):
    id: int
    type: Literal["ip", "llc"]
    inn: str
    name: str
    contact: str
    ogrn: str
    kpp: str
    okved: str
    address: str
    phone: str
    registration: date | None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    business_id: int | None
    is_demo: bool = False
    can_sign: bool = True
    business: BusinessResponse | None = None


class AuthResponse(BaseModel):
    user: UserResponse
    expires_at: datetime
    csrf_token: str


class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    expires_at: datetime
    current: bool


class PasswordChangeRequest(AuthInput):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProfileUpdateRequest(AuthInput):
    name: str = Field(min_length=1, max_length=160)
    contact: str = Field(min_length=1, max_length=100)
    okved: str = Field(default="", pattern=r"^([0-9]{2}(\.[0-9]{1,2}){0,2})?$")
    ogrn: str = Field(default="", pattern=r"^([0-9]{13}|[0-9]{15})?$")
    kpp: str = Field(default="", pattern=r"^([0-9]{9})?$")
    address: str = Field(default="", max_length=250)
    phone: str = Field(default="", max_length=25)
    registration: date | None = None

    @field_validator("name", "contact")
    @classmethod
    def clean_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Заполните название и контактное лицо")
        return value.strip()

    @model_validator(mode="after")
    def check_registration(self):
        if self.registration and self.registration > date.today():
            raise ValueError("Дата регистрации не может быть в будущем")
        return self


class DemoLoginRequest(AuthInput):
    account: Literal["ip", "llc", "admin", "underwriter", "approver"]
