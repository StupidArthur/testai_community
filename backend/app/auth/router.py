from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.models import User, UserRole
from app.auth.schemas import (
    UserRegister, UserLogin, TokenOut, UserOut,
    ResetPasswordRequest, ChangePasswordRequest,
)
from app.auth.service import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_optional_user, RequireRole,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
user_router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/register", response_model=TokenOut)
def register(
    data: UserRegister,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    user_count = db.query(User).count()

    if user_count == 0:
        existing = db.query(User).filter(User.username == data.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )
        user = User(
            username=data.username,
            password_hash=hash_password(data.password),
            role=UserRole.Admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"sub": str(user.id)})
        return TokenOut(
            access_token=token,
            user=UserOut.model_validate(user),
        )

    if current_user is None or current_user.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED
            if current_user is None
            else status.HTTP_403_FORBIDDEN,
            detail="系统已锁定，请联系管理员创建账户",
        )

    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )
    role = UserRole.Admin if data.role == "Admin" else UserRole.Engineer
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenOut)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token = create_access_token({"sub": str(user.id)})
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@user_router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@user_router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole(["Admin"])),
):
    return db.query(User).order_by(User.created_at.desc()).all()


@user_router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole(["Admin"])),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.role == UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能重置其他管理员的密码",
        )
    target.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "密码已重置"}


@user_router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole(["Admin"])),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己",
        )
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        db.delete(target)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该用户存在关联数据，无法删除",
        )
    return {"message": "用户已删除"}


@user_router.post("/me/password")
def change_own_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )
    current_user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "密码已修改"}