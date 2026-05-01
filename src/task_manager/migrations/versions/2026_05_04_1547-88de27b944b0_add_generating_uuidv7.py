"""add generating uuidv7

Revision ID: 88de27b944b0
Revises:
Create Date: 2026-05-04 15:47:37.435864

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "88de27b944b0"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $migration$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_proc p
                WHERE p.proname = 'uuidv7'
                  AND p.prorettype = 'uuid'::regtype
                  AND p.pronargs - p.pronargdefaults = 0
                  AND pg_function_is_visible(p.oid)
            ) THEN
                CREATE EXTENSION IF NOT EXISTS pgcrypto;

                EXECUTE $function$
                    CREATE FUNCTION public.uuidv7()
                    RETURNS uuid
                    LANGUAGE plpgsql
                    PARALLEL SAFE
                    AS $$
                    DECLARE
                        unix_time_ms CONSTANT bytea NOT NULL DEFAULT substring(int8send((extract(epoch FROM clock_timestamp()) * 1000)::bigint) from 3);

                        buffer bytea NOT NULL DEFAULT unix_time_ms || gen_random_bytes(10);
                    BEGIN
                        buffer = set_byte(buffer, 6, (b'0111' || get_byte(buffer, 6)::bit(4))::bit(8)::int);

                        buffer = set_byte(buffer, 8, (b'10'   || get_byte(buffer, 8)::bit(6))::bit(8)::int);

                        RETURN encode(buffer, 'hex');
                    END
                    $$;
                $function$;
            END IF;
        END
        $migration$;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.uuidv7()")
