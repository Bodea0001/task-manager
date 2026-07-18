from uuid import UUID
from typing import TYPE_CHECKING
from datetime import date, datetime, time, timedelta

from sqlalchemy import Index, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import (
    Uuid,
    Text,
    Enum,
    Date,
    Time,
    String,
    Integer,
    Interval,
    TIMESTAMP,
    SmallInteger,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, JSONB

from models.base import Base
from models.dependencies import created_at, uuidpk
from domain.value_objects.tasks import (
    TaskStatus,
    TaskPriority,
    RecurrenceEndMode,
    RecurrenceFrequency,
    RecurrenceOverrideAction,
    RecurrenceBusinessDayPolicy,
)

if TYPE_CHECKING:
    from models.tags import Tag
    from models.users import User


class Task(Base):
    __tablename__ = "task"

    task_id: Mapped[uuidpk]
    title: Mapped[str] = mapped_column(String(250), comment="Заголовок задачи")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Подробное описание задачи"
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, values_callable=lambda enum: [member.value for member in enum]),
        server_default=TaskStatus.ACTIVE,
        comment="Статус задачи",
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, values_callable=lambda enum: [member.value for member in enum]),
        server_default=TaskPriority.NORMAL,
        comment="Приоритет задачи",
    )
    due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), comment="Дедлайн задачи")
    creator_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.user_id"), comment="Идентификатор создателя задачи"
    )
    created_at: Mapped[created_at]
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время окончания задачи"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время мягкого удаления задачи"
    )

    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="task_tag", viewonly=True, order_by="Tag.name"
    )
    creator: Mapped["User"] = relationship("User", back_populates="created_tasks")
    schedule: Mapped["ScheduledTask | None"] = relationship(
        "ScheduledTask",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )

    __table_args__ = (
        CheckConstraint("length(title) > 0", "non_empty_title"),
        CheckConstraint("length(description) > 0", "non_empty_description"),
    )


class ScheduledTask(Base):
    __tablename__ = "scheduled_task"

    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task.task_id"),
        primary_key=True,
        comment="Идентификатор задачи",
    )
    starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), comment="Дата/время начала задачи в расписании"
    )
    ends_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), comment="Дата/время окончания задачи в расписании"
    )

    task: Mapped[Task] = relationship("Task", back_populates="schedule")

    __table_args__ = (
        CheckConstraint(
            "ends_at >= starts_at",
            "correct_interval",
        ),
        Index(
            "ix_scheduled_task_time_range",
            func.tsrange(starts_at, ends_at, "[)"),
            postgresql_using="gist",
        ),
    )


class TaskRecurrenceTemplate(Base):
    __tablename__ = "task_recurrence_template"

    template_id: Mapped[uuidpk]
    creator_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.user_id"), comment="Идентификатор владельца шаблона"
    )
    title: Mapped[str] = mapped_column(String(250), comment="Шаблон заголовка задачи")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Шаблон описания задачи"
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, values_callable=lambda enum: [member.value for member in enum]),
        server_default=TaskPriority.NORMAL,
        comment="Приоритет экземпляров",
    )
    timezone: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Часовой пояс календарных правил"
    )
    created_at: Mapped[created_at]
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время мягкого удаления шаблона"
    )

    rules: Mapped[list["TaskRecurrenceSeries"]] = relationship(
        "TaskRecurrenceSeries",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="task_recurrence_template_tag", viewonly=True, order_by="Tag.name"
    )

    __table_args__ = (
        CheckConstraint("length(title) > 0", "non_empty_title"),
        CheckConstraint("length(description) > 0", "non_empty_description"),
        Index("ix_task_recurrence_template_creator_id", "creator_id"),
    )


class TaskRecurrenceSeries(Base):
    __tablename__ = "task_recurrence_series"

    series_id: Mapped[uuidpk]
    template_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task_recurrence_template.template_id"),
        nullable=False,
        comment="Шаблон, которому принадлежит правило",
    )
    frequency: Mapped[RecurrenceFrequency] = mapped_column(
        Enum(RecurrenceFrequency, values_callable=lambda enum: [member.value for member in enum]),
        comment="Базовая частота повторения",
    )
    step: Mapped[int] = mapped_column(
        Integer, server_default="1", comment="Шаг частоты: каждые N дней/недель/месяцев"
    )
    anchor_date: Mapped[date] = mapped_column(
        Date, comment="Включительная дата начала действия правила"
    )
    default_time: Mapped[time] = mapped_column(Time, comment="Время дедлайна экземпляра")
    default_duration: Mapped[timedelta | None] = mapped_column(
        Interval, nullable=True, comment="Длительность экземпляра с расписанием"
    )
    end_mode: Mapped[RecurrenceEndMode] = mapped_column(
        Enum(RecurrenceEndMode, values_callable=lambda enum: [member.value for member in enum]),
        comment="Тип условия завершения серии",
    )
    repeat_until: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Последняя дата повторения для end_mode=until_date"
    )
    max_occurrences: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Количество повторений для end_mode=count"
    )
    generation_finished_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время остановки генерации правила"
    )
    generation_stop_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Причина остановки генерации правила"
    )
    created_at: Mapped[created_at]
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время мягкого удаления серии"
    )

    template: Mapped[TaskRecurrenceTemplate] = relationship(
        "TaskRecurrenceTemplate",
        back_populates="rules",
    )
    weekdays: Mapped[list["TaskRecurrenceWeekday"]] = relationship(
        "TaskRecurrenceWeekday",
        back_populates="series",
        cascade="all, delete-orphan",
    )
    month_rule: Mapped["TaskRecurrenceMonthRule | None"] = relationship(
        "TaskRecurrenceMonthRule",
        back_populates="series",
        cascade="all, delete-orphan",
    )
    instances: Mapped[list["TaskRecurrenceInstance"]] = relationship(
        "TaskRecurrenceInstance",
        back_populates="series",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("step > 0", "positive_step"),
        CheckConstraint(
            "default_duration IS NULL OR default_duration > INTERVAL '0 seconds'",
            "positive_default_duration",
        ),
        CheckConstraint(
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
            "valid_end_condition",
        ),
        Index("ix_task_recurrence_series_template_id", "template_id"),
        Index("ix_task_recurrence_series_generation_finished_at", "generation_finished_at"),
    )


class TaskRecurrenceWeekday(Base):
    __tablename__ = "task_recurrence_weekday"

    series_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task_recurrence_series.series_id"),
        primary_key=True,
        comment="Идентификатор серии",
    )
    weekday: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        comment="День недели: 1=понедельник, 7=воскресенье",
    )

    series: Mapped[TaskRecurrenceSeries] = relationship(
        "TaskRecurrenceSeries",
        back_populates="weekdays",
    )

    __table_args__ = (CheckConstraint("weekday BETWEEN 1 AND 7", "valid_weekday"),)


class TaskRecurrenceMonthRule(Base):
    __tablename__ = "task_recurrence_month_rule"

    series_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task_recurrence_series.series_id"),
        primary_key=True,
        comment="Идентификатор серии",
    )
    month_day: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="День месяца для повтора"
    )
    week_of_month: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Номер недели месяца; -1 означает последнюю"
    )
    weekday: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="День недели для правила вида 'первый понедельник'"
    )
    business_day_policy: Mapped[RecurrenceBusinessDayPolicy] = mapped_column(
        Enum(
            RecurrenceBusinessDayPolicy,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        server_default=RecurrenceBusinessDayPolicy.NONE,
        comment="Как переносить дату, если нужен рабочий день",
    )

    series: Mapped[TaskRecurrenceSeries] = relationship(
        "TaskRecurrenceSeries",
        back_populates="month_rule",
    )

    __table_args__ = (
        CheckConstraint("month_day IS NULL OR month_day BETWEEN 1 AND 31", "valid_month_day"),
        CheckConstraint(
            "week_of_month IS NULL OR week_of_month BETWEEN -1 AND 5", "valid_week_of_month"
        ),
        CheckConstraint("weekday IS NULL OR weekday BETWEEN 1 AND 7", "valid_month_weekday"),
        CheckConstraint(
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
            "valid_month_rule_shape",
        ),
    )


class TaskRecurrenceInstance(Base):
    __tablename__ = "task_recurrence_instance"

    instance_id: Mapped[uuidpk]
    series_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task_recurrence_series.series_id"),
        nullable=False,
        comment="Серия, которой принадлежит экземпляр",
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task.task_id"),
        nullable=False,
        comment="Созданная задача для экземпляра",
    )
    sequence_no: Mapped[int] = mapped_column(Integer, comment="Порядковый номер в серии")
    planned_date: Mapped[date] = mapped_column(Date, comment="Плановая дата экземпляра")
    planned_starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), nullable=False, comment="Исходные плановые дата и время"
    )
    planned_ends_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), nullable=False, comment="Плановый дедлайн экземпляра"
    )
    is_customized: Mapped[bool] = mapped_column(
        server_default="false", comment="Экземпляр изменен отдельно от серии"
    )
    created_at: Mapped[created_at]
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время мягкого удаления экземпляра"
    )

    series: Mapped[TaskRecurrenceSeries] = relationship(
        "TaskRecurrenceSeries",
        back_populates="instances",
    )
    __table_args__ = (
        CheckConstraint(
            """
            planned_ends_at >= planned_starts_at
            """,
            "valid_planned_interval",
        ),
        CheckConstraint("sequence_no > 0", "positive_sequence_no"),
        Index(
            "ix_task_recurrence_instance_series_sequence", "series_id", "sequence_no", unique=True
        ),
        Index(
            "ix_task_recurrence_instance_active_series_planned_start",
            "series_id",
            "planned_starts_at",
            postgresql_where=deleted_at.is_(None),
        ),
        Index("ix_task_recurrence_instance_task_id", "task_id", unique=True),
        Index("ix_task_recurrence_instance_planned_date", "planned_date"),
        Index("ix_task_recurrence_instance_planned_time", "planned_starts_at", "planned_ends_at"),
    )


class TaskRecurrenceMaterializationConflict(Base):
    __tablename__ = "task_recurrence_materialization_conflict"

    conflict_id: Mapped[uuidpk]
    series_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task_recurrence_series.series_id"),
        nullable=False,
        comment="Серия, экземпляр которой не удалось материализовать",
    )
    sequence_no: Mapped[int] = mapped_column(Integer, comment="Порядковый номер в серии")
    planned_starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), comment="Плановое начало конфликтующего экземпляра"
    )
    planned_ends_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), comment="Плановое окончание конфликтующего экземпляра"
    )
    reason: Mapped[str] = mapped_column(
        String(64),
        server_default="schedule_overlap",
        comment="Причина, по которой экземпляр не был материализован",
    )
    created_at: Mapped[created_at]
    resolved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время разрешения конфликта"
    )

    __table_args__ = (
        CheckConstraint("sequence_no > 0", "positive_sequence_no"),
        CheckConstraint("planned_ends_at >= planned_starts_at", "valid_planned_interval"),
        Index(
            "ix_task_recurrence_materialization_conflict_series_sequence",
            "series_id",
            "sequence_no",
            unique=True,
        ),
        Index(
            "ix_task_recurrence_materialization_conflict_planned_time",
            "planned_starts_at",
            "planned_ends_at",
        ),
        Index(
            "ix_task_recurrence_materialization_conflict_resolved_at",
            "resolved_at",
        ),
    )


class TaskRecurrenceInstanceOverride(Base):
    __tablename__ = "task_recurrence_instance_override"

    series_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task_recurrence_series.series_id"),
        primary_key=True,
        comment="Правило, для которого задано исключение",
    )
    planned_starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False),
        primary_key=True,
        comment="Плановое начало экземпляра до материализации",
    )
    action: Mapped[RecurrenceOverrideAction] = mapped_column(
        Enum(
            RecurrenceOverrideAction, values_callable=lambda enum: [member.value for member in enum]
        ),
        comment="Тип изменения отдельного экземпляра",
    )
    override_starts_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=False), nullable=True, comment="Новое начало экземпляра"
    )
    override_ends_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=False), nullable=True, comment="Новое окончание экземпляра"
    )
    override_title: Mapped[str | None] = mapped_column(
        String(250), nullable=True, comment="Новый заголовок экземпляра"
    )
    override_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Новое описание экземпляра"
    )
    override_due_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=False), nullable=True, comment="Новый дедлайн экземпляра"
    )
    override_priority: Mapped[TaskPriority | None] = mapped_column(
        Enum(TaskPriority, values_callable=lambda enum: [member.value for member in enum]),
        nullable=True,
        comment="Новый приоритет экземпляра",
    )
    patch: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Структурированный patch для будущего экземпляра"
    )
    created_at: Mapped[created_at]
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время мягкого удаления исключения"
    )

    series: Mapped[TaskRecurrenceSeries] = relationship("TaskRecurrenceSeries")

    __table_args__ = (
        CheckConstraint(
            """
            (
                override_starts_at IS NULL
                AND override_ends_at IS NULL
            )
            OR override_ends_at >= override_starts_at
            """,
            "valid_override_interval",
        ),
    )


class TaskStore(Base):
    __tablename__ = "task_store"

    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task.task_id"),
        primary_key=True,
        comment="Идентификатор задачи",
    )
    tsv_content: Mapped[str] = mapped_column(TSVECTOR, comment="Поисковый вектор задачи")

    __table_args__ = (Index("ix_task_store_tsv_content", "tsv_content", postgresql_using="gin"),)
