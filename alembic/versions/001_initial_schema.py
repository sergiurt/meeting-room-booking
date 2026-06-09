"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-09

Creates the full meeting-room booking schema exactly as specified:
btree_gist extension, the rooms and reservations tables (with a generated
duration column, a time-order check, and a GiST exclusion constraint that
prevents overlapping bookings for the same room on the same date), seed rooms,
and the supporting indexes.

Note: `timerange` is not a built-in PostgreSQL range type, so it is created here
(CREATE TYPE ... AS RANGE) to satisfy the locked schema's EXCLUDE constraint.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    # `timerange` is not built in; create it idempotently so the EXCLUDE
    # constraint below can use timerange(start_time, end_time).
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE timerange AS RANGE (subtype = time);
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TABLE rooms (
            room_id     SERIAL          PRIMARY KEY,
            name        VARCHAR(100)    NOT NULL UNIQUE,
            capacity    SMALLINT,
            created_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
        );
        """
    )

    op.execute("INSERT INTO rooms (name) VALUES ('Room A'), ('Room B'), ('Room C');")

    op.execute(
        """
        CREATE TABLE reservations (
            reservation_id  SERIAL          PRIMARY KEY,
            room_id         INTEGER         NOT NULL REFERENCES rooms(room_id) ON DELETE RESTRICT,
            responsible     VARCHAR(150)    NOT NULL,
            res_date        DATE            NOT NULL,
            start_time      TIME            NOT NULL,
            end_time        TIME            NOT NULL,
            duration        INTERVAL        GENERATED ALWAYS AS (end_time - start_time) STORED,
            notes           TEXT,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            CONSTRAINT chk_time_order CHECK (end_time > start_time),
            CONSTRAINT no_room_overlap EXCLUDE USING GIST (
                room_id     WITH =,
                res_date    WITH =,
                timerange(start_time, end_time) WITH &&
            )
        );
        """
    )

    op.execute("CREATE INDEX idx_res_room ON reservations(room_id);")
    op.execute("CREATE INDEX idx_res_date ON reservations(res_date);")
    op.execute("CREATE INDEX idx_res_room_date ON reservations(room_id, res_date);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reservations;")
    op.execute("DROP TABLE IF EXISTS rooms;")
    op.execute("DROP TYPE IF EXISTS timerange;")
