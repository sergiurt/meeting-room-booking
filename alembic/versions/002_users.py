"""users table + seeded admin

Revision ID: 002
Revises: 001
Create Date: 2026-06-10

Adds the users table (username, bcrypt password_hash, role) and seeds a single
admin account from the ADMIN_USERNAME / ADMIN_PASSWORD environment variables
(loaded from .env by alembic/env.py).
"""
import os
from typing import Sequence, Union

import bcrypt
from alembic import op
from sqlalchemy import text

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            user_id       SERIAL        PRIMARY KEY,
            username      VARCHAR(150)  NOT NULL UNIQUE,
            password_hash TEXT          NOT NULL,
            role          VARCHAR(20)   NOT NULL,
            created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT chk_user_role CHECK (role IN ('admin', 'user'))
        );
        """
    )

    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "change-me")
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    bind = op.get_bind()
    bind.execute(
        text(
            "INSERT INTO users (username, password_hash, role) "
            "VALUES (:u, :p, 'admin') ON CONFLICT (username) DO NOTHING"
        ),
        {"u": username, "p": password_hash},
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users;")
