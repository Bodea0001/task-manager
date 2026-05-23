"""make task store trigger statement level

Revision ID: d4e5f6a7b890
Revises: a7c6d5e4b321
Create Date: 2026-05-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b890"
down_revision: Union[str, Sequence[str], None] = "a7c6d5e4b321"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_task_sync_store_tsv_content ON task")
    op.execute("DROP FUNCTION IF EXISTS sync_task_store_tsv_content")

    op.execute("""
        CREATE FUNCTION sync_task_store_tsv_content_statement()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                INSERT INTO task_store(task_id, tsv_content)
                SELECT
                    changed_tasks.task_id,
                    setweight(to_tsvector('russian', COALESCE(changed_tasks.title, '')), 'A') ||
                    setweight(
                        to_tsvector('russian', COALESCE(changed_tasks.description, '')),
                        'B'
                    )
                FROM changed_tasks
                ON CONFLICT (task_id) DO UPDATE
                SET tsv_content = EXCLUDED.tsv_content;
            ELSE
                INSERT INTO task_store(task_id, tsv_content)
                SELECT
                    changed_tasks.task_id,
                    setweight(to_tsvector('russian', COALESCE(changed_tasks.title, '')), 'A') ||
                    setweight(
                        to_tsvector('russian', COALESCE(changed_tasks.description, '')),
                        'B'
                    )
                FROM changed_tasks
                JOIN old_tasks ON old_tasks.task_id = changed_tasks.task_id
                WHERE
                    old_tasks.title IS DISTINCT FROM changed_tasks.title
                    OR old_tasks.description IS DISTINCT FROM changed_tasks.description
                ON CONFLICT (task_id) DO UPDATE
                SET tsv_content = EXCLUDED.tsv_content;
            END IF;

            RETURN NULL;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_task_sync_store_tsv_content_insert
        AFTER INSERT ON task
        REFERENCING NEW TABLE AS changed_tasks
        FOR EACH STATEMENT
        EXECUTE FUNCTION sync_task_store_tsv_content_statement();
    """)
    op.execute("""
        CREATE TRIGGER trg_task_sync_store_tsv_content_update
        AFTER UPDATE ON task
        REFERENCING OLD TABLE AS old_tasks NEW TABLE AS changed_tasks
        FOR EACH STATEMENT
        EXECUTE FUNCTION sync_task_store_tsv_content_statement();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_task_sync_store_tsv_content_update ON task")
    op.execute("DROP TRIGGER IF EXISTS trg_task_sync_store_tsv_content_insert ON task")
    op.execute("DROP FUNCTION IF EXISTS sync_task_store_tsv_content_statement")

    op.execute("""
        CREATE FUNCTION sync_task_store_tsv_content()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO task_store(task_id, tsv_content)
            VALUES (
                NEW.task_id,
                setweight(to_tsvector('russian', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', COALESCE(NEW.description, '')), 'B')
            )
            ON CONFLICT (task_id) DO UPDATE
            SET tsv_content = EXCLUDED.tsv_content;

            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_task_sync_store_tsv_content
        AFTER INSERT OR UPDATE OF title, description ON task
        FOR EACH ROW
        EXECUTE FUNCTION sync_task_store_tsv_content();
    """)
