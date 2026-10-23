from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.auth import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterBase(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=160)


class IPRegisterRequest(RegisterBase):
    type: Literal['ip']
    inn: str = Field(pattern=r"^[0-9]{12}$")


class LegalRegisterRequest(RegisterBase):
    type: Literal['llc']
    inn: str = Field(pattern=r"^[0-9]{10}$")


RegisterRequest = Annotated[
    IPRegisterRequest | LegalRegisterRequest, Field(discriminator='type')
]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    business_id: int | None
