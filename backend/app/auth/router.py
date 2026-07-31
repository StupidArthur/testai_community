from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.auth.models import User, UserRole
from app.auth.schemas import (
    UserRegister, UserLogin, TokenOut, UserOut, UserUpdate,
    ResetPasswordRequest, ChangePasswordRequest,
)
from app.auth.service import (
    hash_password, verify_password, create_access_token,
    get_current_user, RequireRole,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# 灌数占位账号：仅用于展示「无负责人」，禁止登录
_LOGIN_BLOCKED_USERNAMES = frozenset({"无"})


@router.post("/login", response_model=TokenOut)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if user.username in _LOGIN_BLOCKED_USERNAMES:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="占位账号不可登录",
        )
    token = create_access_token({"sub": str(user.id)})
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.post("/add-user", response_model=TokenOut)
def add_user(
    data: UserRegister,
    db: Session = Depends(get_db),
    _admin: User = Depends(RequireRole(["Admin"])),
):
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )
    role_raw = (data.role or "Engineer").strip()
    try:
        role = UserRole(role_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效角色: {role_raw}，可选 Engineer / Manager / Admin",
        ) from exc
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=role,
        real_name=(data.real_name or "").strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(RequireRole(["Admin"])),
):
    """Admin 更新用户真实姓名等资料。"""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    target.real_name = (data.real_name or "").strip()
    db.commit()
    db.refresh(target)
    return UserOut.model_validate(target)


@router.get("/current-user", response_model=UserOut)
def current_user(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.get("/user-list", response_model=list[UserOut])
def user_list(
    db: Session = Depends(get_db),
    _admin: User = Depends(RequireRole(["Admin"])),
):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.put("/password")
def update_password(
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


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(RequireRole(["Admin"])),
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


@router.delete("/{user_id}")
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
