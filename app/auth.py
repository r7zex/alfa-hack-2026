from __future__ import annotations

from typing import TYPE_CHECKING

from pwdlib import PasswordHash
from email_validator import validate_email as check_email
from email_validator import EmailNotValidError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

#if TYPE_CHECKING:
#    from app.db.models.user import User


#_password_hash = PasswordHash().recommended()


