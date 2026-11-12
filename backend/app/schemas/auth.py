from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterIn(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(None, pattern=r"^1\d{10}$")
    password: str = Field(min_length=8, max_length=72)
    nickname: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_identity(self):
        if not self.email and not self.phone:
            raise ValueError("email 或 phone 必填其一")
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    phone: str | None
    nickname: str


class LoginIn(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutOut(BaseModel):
    ok: bool
