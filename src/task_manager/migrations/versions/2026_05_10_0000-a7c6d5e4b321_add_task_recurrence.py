"""add task recurrence

Revision ID: a7c6d5e4b321
Revises: e8f1a2b3c904
Create Date: 2026-05-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7c6d5e4b321"
down_revision: Union[str, Sequence[str], None] = "e8f1a2b3c904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


recurrence_frequency = postgresql.ENUM(
    "daily",
    "weekly",
    "monthly",
    name="recurrencefrequency",
    create_type=False,
)
recurrence_calculation_mode = postgresql.ENUM(
    "scheduled_date",
    "completion_date",
    name="recurrencecalculationmode",
    create_type=False,
)
recurrence_skip_policy = postgresql.ENUM(
    "allow_overdue",
    "create_next_independently",
    "create_next_after_completion",
    "move_to_next_date",
    name="recurrenceskippolicy",
    create_type=False,
)
recurrence_end_mode = postgresql.ENUM(
    "never",
    "until_date",
    "count",
    name="recurrenceendmode",
    create_type=False,
)
recurrence_business_day_policy = postgresql.ENUM(
    "none",
    "next_business_day",
    "previous_business_day",
    name="recurrencebusinessdaypolicy",
    create_type=False,
)
recurrence_override_action = postgresql.ENUM(
    "reschedule",
    "modify",
    "skip",
    "delete",
    name="recurrenceoverrideaction",
    create_type=False,
)
task_priority = postgresql.ENUM(
    "low",
    "normal",
    "high",
    "urgent",
    name="taskpriority",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    for enum_type in _owned_enum_types():
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "task_recurrence_template",
        sa.Column(
            "template_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column("creator_id", sa.Uuid(), nullable=False, comment="Идентификатор владельца"),
        sa.Column("title", sa.String(length=250), nullable=False, comment="Шаблон заголовка"),
        sa.Column("description", sa.Text(), nullable=True, comment="Шаблон описания"),
        sa.Column("priority", task_priority, server_default="normal", nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(title) > 0", name=op.f("ck_task_recurrence_template_non_empty_title")
        ),
        sa.CheckConstraint(
            "length(description) > 0",
            name=op.f("ck_task_recurrence_template_non_empty_description"),
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["user.user_id"],
            name=op.f("fk_task_recurrence_template_creator_id_user"),
        ),
        sa.PrimaryKeyConstraint("template_id", name=op.f("pk_task_recurrence_template")),
    )
    op.create_index(
        op.f("ix_task_recurrence_template_creator_id"),
        "task_recurrence_template",
        ["creator_id"],
    )
    op.create_table(
        "task_recurrence_series",
        sa.Column(
            "series_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "template_id",
            sa.Uuid(),
            nullable=False,
            comment="Шаблон, которому принадлежит правило",
        ),
        sa.Column(
            "frequency",
            recurrence_frequency,
            nullable=False,
            comment="Базовая частота повторения",
        ),
        sa.Column(
            "step",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="Шаг частоты: каждые N дней/недель/месяцев",
        ),
        sa.Column("anchor_date", sa.Date(), nullable=False, comment="Дата первого повторения"),
        sa.Column(
            "default_time",
            sa.Time(),
            nullable=True,
            comment="Время экземпляра, если задача запланирована",
        ),
        sa.Column(
            "default_duration",
            sa.Interval(),
            nullable=True,
            comment="Длительность экземпляра с расписанием",
        ),
        sa.Column(
            "calculation_mode",
            recurrence_calculation_mode,
            nullable=False,
            comment="От какой даты считать следующий экземпляр",
        ),
        sa.Column(
            "skip_policy",
            recurrence_skip_policy,
            nullable=False,
            comment="Что делать с серией при пропуске экземпляра",
        ),
        sa.Column(
            "end_mode",
            recurrence_end_mode,
            nullable=False,
            comment="Тип условия завершения серии",
        ),
        sa.Column(
            "repeat_until",
            sa.Date(),
            nullable=True,
            comment="Последняя дата повторения для end_mode=until_date",
        ),
        sa.Column(
            "max_occurrences",
            sa.Integer(),
            nullable=True,
            comment="Количество повторений для end_mode=count",
        ),
        sa.Column(
            "generation_finished_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время остановки генерации правила",
        ),
        sa.Column(
            "generation_stop_reason",
            sa.String(length=64),
            nullable=True,
            comment="Причина остановки генерации правила",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата/время создания",
        ),
        sa.Column(
            "deleted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время мягкого удаления серии",
        ),
        sa.CheckConstraint("step > 0", name=op.f("ck_task_recurrence_series_positive_step")),
        sa.CheckConstraint(
            "default_duration IS NULL OR default_time IS NOT NULL",
            name=op.f("ck_task_recurrence_series_duration_requires_time"),
        ),
        sa.CheckConstraint(
            """
            (
                end_mode = 'never'
                AND repeat_until IS NULL
                AND max_occurrences IS NULL
            )
            OR (
                end_mode = 'until_date'
                AND repeat_until IS NOT NULL
                AND max_occurrences IS NULL
            )
            OR (
                end_mode = 'count'
                AND repeat_until IS NULL
                AND max_occurrences IS NOT NULL
                AND max_occurrences > 0
            )
            """,
            name=op.f("ck_task_recurrence_series_valid_end_condition"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["task_recurrence_template.template_id"],
            name=op.f("fk_task_recurrence_series_template_id_task_recurrence_template"),
        ),
        sa.PrimaryKeyConstraint("series_id", name=op.f("pk_task_recurrence_series")),
    )
    op.create_index(
        op.f("ix_task_recurrence_series_template_id"),
        "task_recurrence_series",
        ["template_id"],
    )
    op.create_index(
        op.f("ix_task_recurrence_series_generation_finished_at"),
        "task_recurrence_series",
        ["generation_finished_at"],
    )

    op.create_table(
        "task_recurrence_weekday",
        sa.Column("series_id", sa.Uuid(), nullable=False, comment="Идентификатор серии"),
        sa.Column(
            "weekday",
            sa.SmallInteger(),
            nullable=False,
            comment="День недели: 1=понедельник, 7=воскресенье",
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 1 AND 7", name=op.f("ck_task_recurrence_weekday_valid_weekday")
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["task_recurrence_series.series_id"],
            name=op.f("fk_task_recurrence_weekday_series_id_task_recurrence_series"),
        ),
        sa.PrimaryKeyConstraint("series_id", "weekday", name=op.f("pk_task_recurrence_weekday")),
    )

    op.create_table(
        "task_recurrence_month_rule",
        sa.Column("series_id", sa.Uuid(), nullable=False, comment="Идентификатор серии"),
        sa.Column("month_day", sa.Integer(), nullable=True, comment="День месяца для повтора"),
        sa.Column(
            "week_of_month",
            sa.Integer(),
            nullable=True,
            comment="Номер недели месяца; -1 означает последнюю",
        ),
        sa.Column(
            "weekday",
            sa.Integer(),
            nullable=True,
            comment="День недели для правила вида 'первый понедельник'",
        ),
        sa.Column(
            "business_day_policy",
            recurrence_business_day_policy,
            server_default="none",
            nullable=False,
            comment="Как переносить дату, если нужен рабочий день",
        ),
        sa.CheckConstraint(
            "month_day IS NULL OR month_day BETWEEN 1 AND 31",
            name=op.f("ck_task_recurrence_month_rule_valid_month_day"),
        ),
        sa.CheckConstraint(
            "week_of_month IS NULL OR week_of_month BETWEEN -1 AND 5",
            name=op.f("ck_task_recurrence_month_rule_valid_week_of_month"),
        ),
        sa.CheckConstraint(
            "weekday IS NULL OR weekday BETWEEN 1 AND 7",
            name=op.f("ck_task_recurrence_month_rule_valid_month_weekday"),
        ),
        sa.CheckConstraint(
            """
            (
                month_day IS NOT NULL
                AND week_of_month IS NULL
                AND weekday IS NULL
            )
            OR (
                month_day IS NULL
                AND week_of_month IS NOT NULL
                AND weekday IS NOT NULL
            )
            """,
            name=op.f("ck_task_recurrence_month_rule_valid_month_rule_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["task_recurrence_series.series_id"],
            name=op.f("fk_task_recurrence_month_rule_series_id_task_recurrence_series"),
        ),
        sa.PrimaryKeyConstraint("series_id", name=op.f("pk_task_recurrence_month_rule")),
    )

    op.create_table(
        "task_recurrence_instance",
        sa.Column(
            "instance_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "series_id",
            sa.Uuid(),
            nullable=False,
            comment="Серия, которой принадлежит экземпляр",
        ),
        sa.Column(
            "task_id",
            sa.Uuid(),
            nullable=False,
            comment="Созданная задача для экземпляра",
        ),
        sa.Column("sequence_no", sa.Integer(), nullable=False, comment="Порядковый номер в серии"),
        sa.Column("planned_date", sa.Date(), nullable=False, comment="Плановая дата экземпляра"),
        sa.Column(
            "planned_starts_at",
            sa.TIMESTAMP(timezone=False),
            nullable=True,
            comment="Плановое начало, если есть расписание",
        ),
        sa.Column(
            "planned_ends_at",
            sa.TIMESTAMP(timezone=False),
            nullable=True,
            comment="Плановое окончание, если есть расписание",
        ),
        sa.Column(
            "is_customized",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Экземпляр изменен отдельно от серии",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата/время создания",
        ),
        sa.Column(
            "deleted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время мягкого удаления экземпляра",
        ),
        sa.CheckConstraint(
            """
            (
                planned_starts_at IS NULL
                AND planned_ends_at IS NULL
            )
            OR planned_ends_at >= planned_starts_at
            """,
            name=op.f("ck_task_recurrence_instance_valid_planned_interval"),
        ),
        sa.CheckConstraint(
            "sequence_no > 0", name=op.f("ck_task_recurrence_instance_positive_sequence_no")
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["task_recurrence_series.series_id"],
            name=op.f("fk_task_recurrence_instance_series_id_task_recurrence_series"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task.task_id"], name=op.f("fk_task_recurrence_instance_task_id_task")
        ),
        sa.PrimaryKeyConstraint("instance_id", name=op.f("pk_task_recurrence_instance")),
    )
    op.create_index(
        "ix_task_recurrence_instance_series_sequence",
        "task_recurrence_instance",
        ["series_id", "sequence_no"],
        unique=True,
    )
    op.create_index(
        "ix_task_recurrence_instance_task_id",
        "task_recurrence_instance",
        ["task_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_task_recurrence_instance_planned_date"),
        "task_recurrence_instance",
        ["planned_date"],
    )
    op.create_index(
        op.f("ix_task_recurrence_instance_planned_time"),
        "task_recurrence_instance",
        ["planned_starts_at", "planned_ends_at"],
    )
    op.create_table(
        "task_recurrence_materialization_conflict",
        sa.Column(
            "conflict_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "series_id",
            sa.Uuid(),
            nullable=False,
            comment="Серия, для которой не удалось создать экземпляр",
        ),
        sa.Column("sequence_no", sa.Integer(), nullable=False, comment="Порядковый номер в серии"),
        sa.Column(
            "planned_starts_at",
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            comment="Плановое начало конфликтующего экземпляра",
        ),
        sa.Column(
            "planned_ends_at",
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            comment="Плановое окончание конфликтующего экземпляра",
        ),
        sa.Column(
            "reason",
            sa.String(length=64),
            server_default="schedule_overlap",
            nullable=False,
            comment="Причина, по которой экземпляр не был создан",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата/время создания",
        ),
        sa.Column(
            "resolved_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время разрешения конфликта",
        ),
        sa.CheckConstraint(
            "sequence_no > 0",
            name=op.f("ck_task_recurrence_materialization_conflict_positive_sequence_no"),
        ),
        sa.CheckConstraint(
            "planned_ends_at >= planned_starts_at",
            name=op.f("ck_task_recurrence_materialization_conflict_valid_planned_interval"),
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["task_recurrence_series.series_id"],
            name=op.f(
                "fk_task_recurrence_materialization_conflict_series_id_task_recurrence_series"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "conflict_id", name=op.f("pk_task_recurrence_materialization_conflict")
        ),
    )
    op.create_index(
        "ix_task_recurrence_materialization_conflict_series_sequence",
        "task_recurrence_materialization_conflict",
        ["series_id", "sequence_no"],
        unique=True,
    )
    op.create_index(
        op.f("ix_task_recurrence_materialization_conflict_planned_time"),
        "task_recurrence_materialization_conflict",
        ["planned_starts_at", "planned_ends_at"],
    )
    op.create_index(
        op.f("ix_task_recurrence_materialization_conflict_resolved_at"),
        "task_recurrence_materialization_conflict",
        ["resolved_at"],
    )
    op.create_table(
        "task_recurrence_instance_override",
        sa.Column(
            "series_id",
            sa.Uuid(),
            nullable=False,
            comment="Правило, для которого задано исключение",
        ),
        sa.Column(
            "planned_starts_at",
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            comment="Плановое начало экземпляра до материализации",
        ),
        sa.Column(
            "action",
            recurrence_override_action,
            nullable=False,
            comment="Тип изменения отдельного экземпляра",
        ),
        sa.Column(
            "override_starts_at",
            sa.TIMESTAMP(timezone=False),
            nullable=True,
            comment="Новое начало экземпляра",
        ),
        sa.Column(
            "override_ends_at",
            sa.TIMESTAMP(timezone=False),
            nullable=True,
            comment="Новое окончание экземпляра",
        ),
        sa.Column(
            "override_title",
            sa.String(length=250),
            nullable=True,
            comment="Новый заголовок экземпляра",
        ),
        sa.Column(
            "override_description",
            sa.Text(),
            nullable=True,
            comment="Новое описание экземпляра",
        ),
        sa.Column(
            "override_due_at",
            sa.TIMESTAMP(timezone=False),
            nullable=True,
            comment="Новый дедлайн экземпляра",
        ),
        sa.Column(
            "override_priority",
            task_priority,
            nullable=True,
            comment="Новый приоритет экземпляра",
        ),
        sa.Column("patch", postgresql.JSONB(), nullable=True, comment="Patch будущего экземпляра"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата/время создания",
        ),
        sa.Column(
            "deleted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время мягкого удаления исключения",
        ),
        sa.CheckConstraint(
            """
            (
                override_starts_at IS NULL
                AND override_ends_at IS NULL
            )
            OR override_ends_at >= override_starts_at
            """,
            name=op.f("ck_task_recurrence_instance_override_valid_override_interval"),
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["task_recurrence_series.series_id"],
            name=op.f("fk_task_recurrence_instance_override_series_id_task_recurrence_series"),
        ),
        sa.PrimaryKeyConstraint(
            "series_id",
            "planned_starts_at",
            name=op.f("pk_task_recurrence_instance_override"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("task_recurrence_instance_override", if_exists=True)
    op.drop_index(
        op.f("ix_task_recurrence_materialization_conflict_resolved_at"),
        table_name="task_recurrence_materialization_conflict",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_task_recurrence_materialization_conflict_planned_time"),
        table_name="task_recurrence_materialization_conflict",
        if_exists=True,
    )
    op.drop_index(
        "ix_task_recurrence_materialization_conflict_series_sequence",
        table_name="task_recurrence_materialization_conflict",
        if_exists=True,
    )
    op.drop_table("task_recurrence_materialization_conflict", if_exists=True)
    op.drop_index(
        op.f("ix_task_recurrence_instance_planned_time"),
        table_name="task_recurrence_instance",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_task_recurrence_instance_planned_date"),
        table_name="task_recurrence_instance",
        if_exists=True,
    )
    op.drop_index(
        "ix_task_recurrence_instance_task_id",
        table_name="task_recurrence_instance",
        if_exists=True,
    )
    op.drop_index(
        "ix_task_recurrence_instance_series_sequence",
        table_name="task_recurrence_instance",
        if_exists=True,
    )
    op.drop_table("task_recurrence_instance", if_exists=True)
    op.drop_table("task_recurrence_month_rule", if_exists=True)
    op.drop_table("task_recurrence_weekday", if_exists=True)
    op.drop_index(
        op.f("ix_task_recurrence_series_generation_finished_at"),
        table_name="task_recurrence_series",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_task_recurrence_series_template_id"),
        table_name="task_recurrence_series",
        if_exists=True,
    )
    op.drop_table("task_recurrence_series", if_exists=True)
    op.drop_index(
        op.f("ix_task_recurrence_template_creator_id"),
        table_name="task_recurrence_template",
        if_exists=True,
    )
    op.drop_table("task_recurrence_template", if_exists=True)

    for enum_type in reversed(_owned_enum_types()):
        enum_type.drop(op.get_bind(), checkfirst=True)


def _owned_enum_types():
    return (
        recurrence_frequency,
        recurrence_calculation_mode,
        recurrence_skip_policy,
        recurrence_end_mode,
        recurrence_business_day_policy,
        recurrence_override_action,
    )
