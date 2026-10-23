"""Provision an administrator without exposing role selection in public signup.

Usage: python -m app.admin --email admin@example.com
The password is entered privately at the terminal, never as a command argument.
"""

import argparse
import asyncio
from getpass import getpass

from pydantic import TypeAdapter, EmailStr
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal, engine
from app.models.auth import User, UserRole
from app.repositories.auth import user_by_email
from app.security import hash_password


async def create_admin(email: str, password: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            if await user_by_email(db, email):
                raise ValueError("Аккаунт с такой почтой уже существует")
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    role=UserRole.ADMIN,
                )
            )
            try:
                await db.commit()
            except IntegrityError as exc:
                raise ValueError("Аккаунт с такой почтой уже существует") from exc
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Create a database administrator")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower()
    password = getpass("Пароль (8-128 символов): ")
    if not 8 <= len(password) <= 128:
        raise SystemExit("Пароль должен содержать 8-128 символов")
    if password != getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    try:
        asyncio.run(create_admin(email, password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("Администратор создан")


if __name__ == "__main__":
    main()
