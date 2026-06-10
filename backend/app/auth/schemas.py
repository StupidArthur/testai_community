from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str
    password: str = Field(min_length=6, max_length=128, description="密码至少 6 位")
    role: str = "Engineer"


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128, description="新密码至少 6 位")


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128, description="新密码至少 6 位")