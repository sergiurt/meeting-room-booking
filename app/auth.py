"""Authentication helpers: password hashing and current-user dependencies."""
import bcrypt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User


class NotAuthenticated(Exception):
    """Raised when a protected route is accessed without a valid session."""


class NotAuthorized(Exception):
    """Raised when an authenticated user lacks the required role."""


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return await session.get(User, user_id)


async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise NotAuthenticated()
    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    if user.role != "admin":
        raise NotAuthorized()
    return user
