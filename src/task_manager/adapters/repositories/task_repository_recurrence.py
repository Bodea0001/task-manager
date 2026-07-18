from uuid import UUID
from typing import Literal
from datetime import datetime, time, timedelta

from sqlalchemy import (
    text,
    func,
    cast as sql_cast,
    select,
    union_all,
    insert,
    update,
    literal,
    bindparam,
)
from sqlalchemy.types import Uuid, TIMESTAMP
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import CTE
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by, insert as pg_insert

import exceptions as app_exc
from config import settings
from dto.tasks import (
    AddTaskRecurrence,
    AddTaskRecurrenceTemplate,
    UpdateTaskRecurrence,
    ListTaskRecurrenceTemplatesFilters,
)
from models.tags import Tag as TagModel
from models.tasks import (
    Task as TaskModel,
    TaskRecurrenceSeries as TaskRecurrenceSeriesModel,
    TaskRecurrenceWeekday as TaskRecurrenceWeekdayModel,
    TaskRecurrenceTemplate as TaskRecurrenceTemplateModel,
    TaskRecurrenceInstance as TaskRecurrenceInstanceModel,
    TaskRecurrenceMonthRule as TaskRecurrenceMonthRuleModel,
)
from models.task_tags import TaskRecurrenceTemplateTag as TaskRecurrenceTemplateTagModel
from domain.recurrences import recurrence_end_mode
from domain.value_objects.tasks import (
    Schedule,
    TaskStatus,
    TaskRecurrence,
    RecurrenceEndMode,
    TaskRecurrenceTemplate,
    RecurrenceBusinessDayPolicy,
)
from adapters.repositories.task_repository_common import (
    TaskRepositoryCommon,
    translate_repository_errors,
)


class TaskRecurrenceMixin(TaskRepositoryCommon):
    async def materialize_recurrence_instances(
        self,
        user_id: UUID,
        windows: tuple[Schedule, ...],
    ) -> None:
        await self.materialize_recurrence_instances_for_owners((user_id,), windows)

    async def materialize_recurrence_instances_for_owners(
        self,
        user_ids: tuple[UUID, ...],
        windows: tuple[Schedule, ...],
    ) -> None:
        if not user_ids or not windows:
            return

        stmt = text("""
            WITH requested_window AS (
                SELECT
                    starts_at::date AS starts_on,
                    CASE frequency_cap.frequency
                        WHEN 'monthly' THEN least(
                            ends_at::date,
                            starts_at::date
                            + (
                                CAST(:monthly_materialization_days AS integer)
                                * INTERVAL '1 day'
                            )
                        )::date
                        ELSE least(
                            ends_at::date,
                            starts_at::date
                            + (
                                CASE frequency_cap.frequency
                                    WHEN 'weekly' THEN CAST(:weekly_materialization_days AS integer)
                                    ELSE CAST(:daily_materialization_days AS integer)
                                END * INTERVAL '1 day'
                            )
                        )::date
                    END AS ends_on,
                    frequency_cap.frequency
                FROM unnest(
                    CAST(:window_starts AS timestamp[]),
                    CAST(:window_ends AS timestamp[])
                ) AS requested(starts_at, ends_at)
                CROSS JOIN (
                    VALUES ('daily'), ('weekly'), ('monthly')
                ) AS frequency_cap(frequency)
            ),
            owner_input AS MATERIALIZED (
                SELECT unnest(CAST(:user_ids AS uuid[])) AS creator_id
            ),
            owner_template AS MATERIALIZED (
                SELECT
                    task_recurrence_template.template_id,
                    task_recurrence_template.title,
                    task_recurrence_template.description,
                    task_recurrence_template.priority,
                    task_recurrence_template.creator_id
                FROM owner_input
                JOIN task_recurrence_template
                    ON task_recurrence_template.creator_id = owner_input.creator_id
                WHERE task_recurrence_template.deleted_at IS NULL
            ),
            series_window AS (
                SELECT
                    task_recurrence_series.series_id,
                    task_recurrence_series.template_id,
                    task_recurrence_series.frequency::varchar AS frequency,
                    task_recurrence_series.step,
                    task_recurrence_series.anchor_date,
                    task_recurrence_series.default_time,
                    task_recurrence_series.default_duration,
                    task_recurrence_series.repeat_until,
                    task_recurrence_series.max_occurrences,
                    ARRAY(
                        SELECT task_recurrence_weekday.weekday::smallint
                        FROM task_recurrence_weekday
                        WHERE
                            task_recurrence_weekday.series_id
                                = task_recurrence_series.series_id
                        ORDER BY task_recurrence_weekday.weekday
                    )::smallint[] AS weekdays,
                    task_recurrence_month_rule.month_day,
                    task_recurrence_month_rule.week_of_month,
                    task_recurrence_month_rule.weekday AS month_weekday,
                    task_recurrence_month_rule.business_day_policy::varchar
                        AS business_day_policy,
                    owner_template.title,
                    owner_template.description,
                    owner_template.priority,
                    owner_template.creator_id,
                    requested_window.starts_on,
                    requested_window.ends_on
                FROM owner_template
                JOIN task_recurrence_series
                    ON task_recurrence_series.template_id = owner_template.template_id
                LEFT JOIN task_recurrence_month_rule
                    ON task_recurrence_month_rule.series_id = task_recurrence_series.series_id
                JOIN requested_window
                    ON requested_window.frequency = task_recurrence_series.frequency::varchar
                    AND requested_window.ends_on >= task_recurrence_series.anchor_date
                WHERE
                    task_recurrence_series.deleted_at IS NULL
                    AND task_recurrence_series.generation_finished_at IS NULL
            ),
            candidate AS MATERIALIZED (
                SELECT DISTINCT ON (series_id, sequence_no)
                    uuidv7() AS task_id,
                    series_window.series_id,
                    series_window.template_id,
                    COALESCE(occurrence_override.override_title, series_window.title) AS title,
                    COALESCE(
                        occurrence_override.override_description,
                        series_window.description
                    ) AS description,
                    COALESCE(occurrence_override.override_priority, series_window.priority)
                        AS priority,
                    series_window.creator_id,
                    occurrence.sequence_no,
                    occurrence.planned_date,
                    COALESCE(
                        occurrence_override.override_starts_at,
                        occurrence.planned_date::timestamp + series_window.default_time
                    ) AS planned_starts_at,
                    COALESCE(
                        occurrence_override.override_ends_at,
                        occurrence.planned_date::timestamp
                        + series_window.default_time
                        + COALESCE(series_window.default_duration, INTERVAL '0 seconds')
                    ) AS planned_ends_at,
                    series_window.default_duration IS NOT NULL AS has_schedule,
                    series_window.ends_on
                FROM series_window
                CROSS JOIN LATERAL generate_task_recurrence_dates(
                    series_window.frequency,
                    series_window.step,
                    series_window.anchor_date,
                    series_window.weekdays,
                    series_window.month_day,
                    series_window.week_of_month,
                    series_window.month_weekday,
                    series_window.business_day_policy,
                    series_window.starts_on,
                    series_window.ends_on,
                    series_window.repeat_until,
                    series_window.max_occurrences
                ) AS occurrence
                LEFT JOIN task_recurrence_instance_override AS occurrence_override
                    ON occurrence_override.series_id = series_window.series_id
                    AND occurrence_override.planned_starts_at = (
                        occurrence.planned_date::timestamp + series_window.default_time
                    )
                    AND occurrence_override.deleted_at IS NULL
                WHERE
                    occurrence.planned_date >= series_window.starts_on
                    AND occurrence.planned_date <= series_window.ends_on
                    AND (
                        occurrence_override.action IS NULL
                        OR occurrence_override.action NOT IN ('skip', 'delete')
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM task_recurrence_instance existing_instance
                        WHERE
                            existing_instance.series_id = series_window.series_id
                            AND existing_instance.sequence_no = occurrence.sequence_no
                            AND existing_instance.deleted_at IS NULL
                    )
                ORDER BY series_id, sequence_no, ends_on DESC
            ),
            blocking_schedule AS MATERIALIZED (
                SELECT
                    blocking_task.creator_id,
                    scheduled_task.starts_at,
                    scheduled_task.ends_at
                FROM scheduled_task
                CROSS JOIN LATERAL (
                    SELECT task.creator_id
                    FROM task
                    WHERE
                        task.task_id = scheduled_task.task_id
                        AND task.deleted_at IS NULL
                        AND task.status != 'cancelled'
                    OFFSET 0
                ) AS blocking_task
                JOIN owner_input
                    ON owner_input.creator_id = blocking_task.creator_id
                WHERE
                    tsrange(
                        scheduled_task.starts_at,
                        scheduled_task.ends_at,
                        '[)'
                    ) && tsrange(
                        (SELECT min(starts_on)::timestamp FROM requested_window),
                        (
                            SELECT (max(ends_on) + 1)::timestamp
                            FROM requested_window
                        ),
                        '[)'
                    )
            ),
            schedule_conflict AS MATERIALIZED (
                SELECT DISTINCT candidate.series_id, candidate.sequence_no
                FROM candidate
                JOIN blocking_schedule
                    ON blocking_schedule.creator_id = candidate.creator_id
                    AND blocking_schedule.starts_at < candidate.planned_ends_at
                    AND blocking_schedule.ends_at > candidate.planned_starts_at
                WHERE
                    candidate.has_schedule
            ),
            conflict_candidate AS MATERIALIZED (
                SELECT
                    candidate.*,
                    schedule_conflict.series_id IS NOT NULL AS has_schedule_conflict
                FROM candidate
                LEFT JOIN schedule_conflict
                    ON schedule_conflict.series_id = candidate.series_id
                    AND schedule_conflict.sequence_no = candidate.sequence_no
            ),
            task_values AS MATERIALIZED (
                SELECT
                    conflict_candidate.task_id,
                    conflict_candidate.series_id,
                    conflict_candidate.sequence_no,
                    conflict_candidate.template_id,
                    conflict_candidate.title,
                    conflict_candidate.description,
                    conflict_candidate.priority,
                    conflict_candidate.creator_id,
                    conflict_candidate.planned_starts_at,
                    conflict_candidate.planned_ends_at,
                    conflict_candidate.has_schedule
                FROM conflict_candidate
                WHERE NOT conflict_candidate.has_schedule_conflict
            ),
            conflict_values AS MATERIALIZED (
                SELECT
                    conflict_candidate.series_id,
                    conflict_candidate.sequence_no,
                    conflict_candidate.planned_starts_at,
                    conflict_candidate.planned_ends_at
                FROM conflict_candidate
                WHERE conflict_candidate.has_schedule_conflict
            ),
            inserted_task AS (
                INSERT INTO task(
                    task_id,
                    title,
                    description,
                    status,
                    priority,
                    due_at,
                    creator_id
                )
                SELECT
                    task_values.task_id,
                    task_values.title,
                    task_values.description,
                    'active',
                    task_values.priority,
                    task_values.planned_ends_at,
                    task_values.creator_id
                FROM task_values
                RETURNING task_id
            ),
            inserted_instance AS (
                INSERT INTO task_recurrence_instance(
                    series_id,
                    task_id,
                    sequence_no,
                    planned_date,
                    planned_starts_at,
                    planned_ends_at,
                    is_customized
                )
                SELECT
                    task_values.series_id,
                    task_values.task_id,
                    task_values.sequence_no,
                    task_values.planned_starts_at::date,
                    task_values.planned_starts_at,
                    task_values.planned_ends_at,
                    false
                FROM task_values
                JOIN inserted_task ON inserted_task.task_id = task_values.task_id
                ON CONFLICT (series_id, sequence_no) DO NOTHING
                RETURNING task_id
            ),
            inserted_schedule AS (
                INSERT INTO scheduled_task(task_id, starts_at, ends_at)
                SELECT
                    task_values.task_id,
                    task_values.planned_starts_at,
                    task_values.planned_ends_at
                FROM task_values
                JOIN inserted_task ON inserted_task.task_id = task_values.task_id
                WHERE task_values.has_schedule
                RETURNING task_id
            ),
            inserted_conflict AS (
                INSERT INTO task_recurrence_materialization_conflict(
                    series_id,
                    sequence_no,
                    planned_starts_at,
                    planned_ends_at,
                    reason,
                    resolved_at
                )
                SELECT
                    conflict_values.series_id,
                    conflict_values.sequence_no,
                    conflict_values.planned_starts_at,
                    conflict_values.planned_ends_at,
                    'schedule_overlap',
                    NULL
                FROM conflict_values
                ON CONFLICT (series_id, sequence_no) DO UPDATE SET
                    planned_starts_at = EXCLUDED.planned_starts_at,
                    planned_ends_at = EXCLUDED.planned_ends_at,
                    reason = EXCLUDED.reason,
                    resolved_at = NULL
                RETURNING conflict_id
            ),
            resolved_conflict AS (
                UPDATE task_recurrence_materialization_conflict
                SET resolved_at = now()
                FROM task_values
                WHERE
                    task_recurrence_materialization_conflict.series_id
                        = task_values.series_id
                    AND task_recurrence_materialization_conflict.sequence_no
                        = task_values.sequence_no
                    AND task_recurrence_materialization_conflict.resolved_at IS NULL
                RETURNING conflict_id
            ),
            inserted_tags AS (
                INSERT INTO task_tag(task_id, tag_id)
                SELECT
                    task_values.task_id,
                    task_recurrence_template_tag.tag_id
                FROM task_values
                JOIN inserted_task ON inserted_task.task_id = task_values.task_id
                JOIN task_recurrence_template_tag
                    ON task_recurrence_template_tag.template_id = task_values.template_id
                JOIN tag
                    ON tag.tag_id = task_recurrence_template_tag.tag_id
                    AND tag.creator_id = task_values.creator_id
                    AND tag.deleted_at IS NULL
                ON CONFLICT (task_id, tag_id) DO NOTHING
                RETURNING task_id
            )
            SELECT
                (SELECT count(*) FROM inserted_instance) AS inserted_count,
                (SELECT count(*) FROM inserted_conflict) AS conflict_count,
                (SELECT count(*) FROM resolved_conflict) AS resolved_conflict_count
        """).bindparams(
            bindparam("user_ids", type_=ARRAY(Uuid(as_uuid=True))),
            bindparam("window_starts", type_=ARRAY(TIMESTAMP(timezone=False))),
            bindparam("window_ends", type_=ARRAY(TIMESTAMP(timezone=False))),
        )

        await self.session.execute(
            stmt,
            {
                "user_ids": user_ids,
                "window_starts": [window.starts_at for window in windows],
                "window_ends": [window.ends_at for window in windows],
                "daily_materialization_days": settings.recurrence.daily_materialization_days,
                "weekly_materialization_days": settings.recurrence.weekly_materialization_days,
                "monthly_materialization_days": settings.recurrence.monthly_materialization_days,
            },
        )

    @translate_repository_errors
    async def add_task_recurrence_template(
        self,
        user_id: UUID,
        data: AddTaskRecurrenceTemplate,
    ) -> TaskRecurrenceTemplate:
        await self._raise_if_recurrence_schedules_overlap(user_id=user_id, rules=data.rules)
        tag_ids = tuple(set(data.tag_ids))
        if tag_ids:
            await self._raise_if_tags_do_not_belong_to_user(user_id, set(tag_ids))

        stmt = text("""
            WITH rule_input AS MATERIALIZED (
                SELECT
                    uuidv7() AS series_id,
                    rule.frequency,
                    rule.interval,
                    rule.anchor_date,
                    rule.default_time,
                    rule.default_duration_seconds,
                    rule.weekdays,
                    rule.month_rule,
                    rule.repeat_until,
                    rule.occurrences_limit
                FROM jsonb_to_recordset(CAST(:rules AS jsonb)) AS rule(
                    frequency text,
                    interval integer,
                    anchor_date date,
                    default_time time,
                    default_duration_seconds double precision,
                    weekdays jsonb,
                    month_rule jsonb,
                    repeat_until date,
                    occurrences_limit integer
                )
            ),
            inserted_template AS (
                INSERT INTO task_recurrence_template(
                    creator_id,
                    title,
                    description,
                    priority
                )
                VALUES (
                    :user_id,
                    :title,
                    :description,
                    CAST(:priority AS taskpriority)
                )
                RETURNING
                    template_id,
                    title,
                    description,
                    priority,
                    created_at
            ),
            tag_input AS MATERIALIZED (
                SELECT DISTINCT tag_id
                FROM unnest(CAST(:tag_ids AS uuid[])) AS tag_input(tag_id)
            ),
            inserted_template_tag AS (
                INSERT INTO task_recurrence_template_tag(template_id, tag_id)
                SELECT
                    inserted_template.template_id,
                    tag_input.tag_id
                FROM inserted_template
                CROSS JOIN tag_input
                ON CONFLICT (template_id, tag_id) DO NOTHING
                RETURNING template_id
            ),
            inserted_series AS (
                INSERT INTO task_recurrence_series(
                    series_id,
                    template_id,
                    frequency,
                    step,
                    anchor_date,
                    default_time,
                    default_duration,
                    end_mode,
                    repeat_until,
                    max_occurrences
                )
                SELECT
                    rule_input.series_id,
                    inserted_template.template_id,
                    rule_input.frequency::recurrencefrequency,
                    rule_input.interval,
                    rule_input.anchor_date,
                    rule_input.default_time,
                    CASE
                        WHEN rule_input.default_duration_seconds IS NULL THEN NULL
                        ELSE make_interval(secs => rule_input.default_duration_seconds)
                    END,
                    CASE
                        WHEN rule_input.repeat_until IS NOT NULL THEN 'until_date'
                        WHEN rule_input.occurrences_limit IS NOT NULL THEN 'count'
                        ELSE 'never'
                    END::recurrenceendmode,
                    rule_input.repeat_until,
                    rule_input.occurrences_limit
                FROM rule_input
                CROSS JOIN inserted_template
                RETURNING
                    series_id,
                    template_id,
                    frequency,
                    step,
                    anchor_date,
                    default_time,
                    default_duration,
                    repeat_until,
                    max_occurrences
            ),
            inserted_weekday AS (
                INSERT INTO task_recurrence_weekday(series_id, weekday)
                SELECT
                    inserted_series.series_id,
                    weekday.value::int
                FROM inserted_series
                JOIN rule_input ON rule_input.series_id = inserted_series.series_id
                CROSS JOIN LATERAL jsonb_array_elements_text(rule_input.weekdays) AS weekday(value)
                WHERE inserted_series.frequency = 'weekly'
                ON CONFLICT (series_id, weekday) DO NOTHING
                RETURNING series_id
            ),
            inserted_month_rule AS (
                INSERT INTO task_recurrence_month_rule(
                    series_id,
                    month_day,
                    week_of_month,
                    weekday,
                    business_day_policy
                )
                SELECT
                    inserted_series.series_id,
                    (rule_input.month_rule ->> 'month_day')::int,
                    (rule_input.month_rule ->> 'week_of_month')::int,
                    (rule_input.month_rule ->> 'weekday')::int,
                    COALESCE(
                        rule_input.month_rule ->> 'business_day_policy',
                        'none'
                    )::recurrencebusinessdaypolicy
                FROM inserted_series
                JOIN rule_input ON rule_input.series_id = inserted_series.series_id
                WHERE inserted_series.frequency = 'monthly'
                ON CONFLICT (series_id) DO NOTHING
                RETURNING series_id
            )
            SELECT
                inserted_template.template_id,
                (SELECT count(*) FROM inserted_template_tag) AS inserted_tag_count,
                (SELECT count(*) FROM inserted_series) AS inserted_series_count,
                (SELECT count(*) FROM inserted_weekday) AS inserted_weekday_count,
                (SELECT count(*) FROM inserted_month_rule) AS inserted_month_rule_count
            FROM inserted_template
        """).bindparams(bindparam("tag_ids", type_=ARRAY(Uuid())))
        result = await self.session.execute(
            stmt,
            {
                "user_id": user_id,
                "title": data.title,
                "description": data.description,
                "priority": data.priority.value,
                "rules": self._recurrence_rules_json(data.rules),
                "tag_ids": list(tag_ids),
            },
        )
        template_id = result.one().template_id
        await self.materialize_recurrence_instances(
            user_id,
            tuple(self._initial_materialization_window(rule) for rule in data.rules),
        )
        return await self.get_task_recurrence_template(user_id, template_id)

    async def get_task_recurrence_template(
        self,
        user_id: UUID,
        template_id: UUID,
    ) -> TaskRecurrenceTemplate:
        template_page = (
            select(TaskRecurrenceTemplateModel.template_id)
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.template_id == template_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
            )
            .cte("template_page")
        )
        stmt = self._select_recurrence_template_rows(template_page)
        result = await self.session.execute(stmt)
        rows = result.all()
        if not rows:
            raise app_exc.RecurrenceTemplateNotFound
        return self._rows_to_recurrence_template(rows)

    async def get_task_recurrence_templates(
        self, user_id: UUID, filters: ListTaskRecurrenceTemplatesFilters
    ) -> list[TaskRecurrenceTemplate]:
        template_page = (
            select(TaskRecurrenceTemplateModel.template_id)
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                *self._build_recurrence_template_filters(filters),
            )
            .order_by(
                TaskRecurrenceTemplateModel.created_at.desc(),
                TaskRecurrenceTemplateModel.template_id.desc(),
            )
            .limit(filters.limit)
            .offset(filters.offset)
            .cte("template_page")
        )
        result = await self.session.execute(self._select_recurrence_template_rows(template_page))
        return self._rows_to_recurrence_templates(result.all())

    async def count_task_recurrence_templates(
        self, user_id: UUID, filters: ListTaskRecurrenceTemplatesFilters
    ) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(TaskRecurrenceTemplateModel)
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                *self._build_recurrence_template_filters(filters),
            )
        )
        return result.scalar_one()

    @translate_repository_errors(not_found=app_exc.RecurrenceTemplateNotFound)
    async def delete_task_recurrence_template(self, user_id: UUID, template_id: UUID) -> None:
        now = func.now()
        owner_template = self._owned_recurrence_template(user_id, template_id).cte("owner_template")
        series_ids = select(TaskRecurrenceSeriesModel.series_id).where(
            TaskRecurrenceSeriesModel.template_id.in_(select(owner_template.c.template_id)),
            TaskRecurrenceSeriesModel.deleted_at.is_(None),
        )
        removable_instances = self._removable_recurrence_instances(
            user_id=user_id,
            series_condition=TaskRecurrenceInstanceModel.series_id.in_(series_ids),
            cte_name="removable_recurrence_template_instances",
        )
        deleted_tasks = (
            update(TaskModel)
            .values(deleted_at=now)
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id.in_(select(removable_instances.c.task_id)),
                self._task_is_not_deleted(),
            )
            .returning(TaskModel.task_id)
            .cte("deleted_recurrence_template_tasks")
        )
        deleted_instances = (
            update(TaskRecurrenceInstanceModel)
            .values(deleted_at=now)
            .where(
                TaskRecurrenceInstanceModel.instance_id.in_(
                    select(removable_instances.c.instance_id)
                ),
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .returning(TaskRecurrenceInstanceModel.instance_id)
            .cte("deleted_recurrence_template_instances")
        )
        deleted_series = (
            update(TaskRecurrenceSeriesModel)
            .values(deleted_at=now)
            .where(
                TaskRecurrenceSeriesModel.template_id.in_(select(owner_template.c.template_id)),
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
            .returning(TaskRecurrenceSeriesModel.series_id)
            .cte("deleted_recurrence_template_series")
        )
        deleted_template = (
            update(TaskRecurrenceTemplateModel)
            .values(deleted_at=now)
            .where(
                TaskRecurrenceTemplateModel.template_id.in_(select(owner_template.c.template_id)),
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
            )
            .returning(TaskRecurrenceTemplateModel.template_id)
            .cte("deleted_recurrence_template")
        )
        result = await self.session.execute(
            select(select(1).select_from(deleted_template).exists())
            .add_cte(deleted_tasks)
            .add_cte(deleted_instances)
            .add_cte(deleted_series)
        )
        if not result.scalar_one():
            raise app_exc.RecurrenceTemplateNotFound

    @translate_repository_errors(not_found=app_exc.RecurrenceTemplateNotFound)
    async def add_tag_to_task_recurrence_template(
        self, user_id: UUID, template_id: UUID, tag_id: UUID
    ) -> TaskRecurrenceTemplate:
        await self._sync_recurrence_template_tag(
            user_id=user_id,
            template_id=template_id,
            tag_id=tag_id,
            action="add",
        )
        return await self.get_task_recurrence_template(user_id, template_id)

    @translate_repository_errors(not_found=app_exc.RecurrenceTemplateNotFound)
    async def delete_tag_from_task_recurrence_template(
        self, user_id: UUID, template_id: UUID, tag_id: UUID
    ) -> TaskRecurrenceTemplate:
        await self._sync_recurrence_template_tag(
            user_id=user_id,
            template_id=template_id,
            tag_id=tag_id,
            action="delete",
        )
        return await self.get_task_recurrence_template(user_id, template_id)

    @translate_repository_errors(not_found=app_exc.RecurrenceTemplateNotFound)
    async def add_task_recurrence_rule(
        self, user_id: UUID, template_id: UUID, data: AddTaskRecurrence
    ) -> TaskRecurrence:
        await self._raise_if_recurrence_template_does_not_belong_to_user(user_id, template_id)
        await self._raise_if_recurrence_schedule_overlaps(
            user_id=user_id, task_id=None, recurrence_id=None, data=data
        )
        inserted_series = self._insert_recurrence_series_for_template(
            self._owned_recurrence_template(user_id, template_id).cte("owner_template"),
            data,
        )
        inserted_weekday = self._insert_recurrence_weekdays(inserted_series, data)
        inserted_month_rule = self._insert_recurrence_month_rule(inserted_series, data)
        stmt = (
            select(inserted_series.c.series_id)
            .add_cte(inserted_weekday)
            .add_cte(inserted_month_rule)
        )
        result = await self.session.execute(stmt)
        recurrence_id = result.scalar_one()
        await self.materialize_recurrence_instances(
            user_id,
            (self._initial_materialization_window(data),),
        )
        return await self._get_recurrence(user_id, recurrence_id)

    async def get_task_recurrence_rules(
        self, user_id: UUID, template_id: UUID
    ) -> list[TaskRecurrence]:
        await self._raise_if_recurrence_template_does_not_belong_to_user(user_id, template_id)
        stmt = (
            select(TaskRecurrenceSeriesModel)
            .options(
                selectinload(TaskRecurrenceSeriesModel.weekdays),
                selectinload(TaskRecurrenceSeriesModel.month_rule),
            )
            .join(
                TaskRecurrenceTemplateModel,
                TaskRecurrenceTemplateModel.template_id == TaskRecurrenceSeriesModel.template_id,
            )
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.template_id == template_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
            .order_by(TaskRecurrenceSeriesModel.anchor_date, TaskRecurrenceSeriesModel.created_at)
        )
        result = await self.session.execute(stmt)
        return [self._model_to_recurrence(model) for model in result.scalars()]

    @translate_repository_errors(not_found=app_exc.RecurrenceRuleNotFound)
    async def get_recurrence(self, user_id: UUID, recurrence_id: UUID) -> TaskRecurrence:
        return await self._get_recurrence(user_id, recurrence_id)

    @translate_repository_errors(not_found=app_exc.RecurrenceRuleNotFound)
    async def get_recurrence_template_id(self, user_id: UUID, recurrence_id: UUID) -> UUID:
        stmt = (
            select(TaskRecurrenceSeriesModel.template_id)
            .join(
                TaskRecurrenceTemplateModel,
                TaskRecurrenceTemplateModel.template_id == TaskRecurrenceSeriesModel.template_id,
            )
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                TaskRecurrenceSeriesModel.series_id == recurrence_id,
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_recurrence_owner_ids_requiring_materialization(
        self, window: Schedule
    ) -> tuple[UUID, ...]:
        last_instance_sequence = (
            select(TaskRecurrenceInstanceModel.sequence_no.label("sequence_no"))
            .where(
                TaskRecurrenceSeriesModel.max_occurrences.is_not(None),
                TaskRecurrenceInstanceModel.series_id == TaskRecurrenceSeriesModel.series_id,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .order_by(TaskRecurrenceInstanceModel.sequence_no.desc())
            .limit(1)
            .lateral("last_instance_sequence")
        )
        last_instance_time = (
            select(TaskRecurrenceInstanceModel.planned_starts_at.label("planned_starts_at"))
            .where(
                TaskRecurrenceInstanceModel.series_id == TaskRecurrenceSeriesModel.series_id,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .order_by(TaskRecurrenceInstanceModel.planned_starts_at.desc())
            .limit(1)
            .lateral("last_instance_time")
        )
        stmt = (
            select(TaskRecurrenceTemplateModel.creator_id)
            .join(
                TaskRecurrenceSeriesModel,
                TaskRecurrenceSeriesModel.template_id == TaskRecurrenceTemplateModel.template_id,
            )
            .outerjoin(last_instance_sequence, literal(True))
            .outerjoin(last_instance_time, literal(True))
            .where(
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
                TaskRecurrenceSeriesModel.generation_finished_at.is_(None),
                TaskRecurrenceSeriesModel.anchor_date <= window.ends_at.date(),
                (
                    TaskRecurrenceSeriesModel.repeat_until.is_(None)
                    | (TaskRecurrenceSeriesModel.repeat_until >= window.starts_at.date())
                ),
                (
                    TaskRecurrenceSeriesModel.max_occurrences.is_(None)
                    | (
                        func.coalesce(last_instance_sequence.c.sequence_no, 0)
                        < TaskRecurrenceSeriesModel.max_occurrences
                    )
                ),
                (
                    last_instance_time.c.planned_starts_at.is_(None)
                    | (last_instance_time.c.planned_starts_at < window.ends_at)
                ),
            )
            .distinct()
            .order_by(TaskRecurrenceTemplateModel.creator_id)
        )
        result = await self.session.execute(stmt)
        return tuple(result.scalars())

    @translate_repository_errors(not_found=app_exc.RecurrenceRuleNotFound)
    async def update_task_recurrence(
        self, user_id: UUID, recurrence_id: UUID, data: UpdateTaskRecurrence
    ) -> TaskRecurrence:
        await self._raise_if_recurrence_does_not_belong_to_user(user_id, recurrence_id)
        current_recurrence = await self._get_recurrence(user_id, recurrence_id)
        await self._raise_if_recurrence_schedule_overlaps(
            user_id=user_id,
            task_id=None,
            recurrence_id=recurrence_id,
            data=data,
            current_recurrence=current_recurrence,
        )

        result = await self.session.execute(
            update(TaskRecurrenceSeriesModel)
            .values(**self._recurrence_update_values(data))
            .where(
                TaskRecurrenceSeriesModel.series_id == recurrence_id,
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
            .returning(TaskRecurrenceSeriesModel.series_id)
        )
        result.scalar_one()
        await self.recalculate_future_recurrence_instances(
            user_id=user_id,
            recurrence_id=recurrence_id,
            from_datetime=min(
                datetime.combine(current_recurrence.anchor_date, time.min),
                datetime.combine(data.anchor_date, time.min),
            ),
        )
        await self.materialize_recurrence_instances(
            user_id,
            (
                self._continuing_materialization_window(
                    data,
                    frequency=current_recurrence.frequency,
                ),
            ),
        )
        return await self._get_recurrence(user_id, recurrence_id)

    @translate_repository_errors(not_found=app_exc.RecurrenceRuleNotFound)
    async def stop_task_recurrence(
        self, user_id: UUID, recurrence_id: UUID, stop_from: datetime
    ) -> TaskRecurrence:
        repeat_until = stop_from.date() - timedelta(days=1)
        owner_series = self._owned_recurrence_series(user_id, recurrence_id).cte("owner_series")
        result = await self.session.execute(
            update(TaskRecurrenceSeriesModel)
            .values(
                end_mode=RecurrenceEndMode.UNTIL_DATE,
                repeat_until=repeat_until,
                max_occurrences=None,
                generation_finished_at=func.now(),
                generation_stop_reason="stopped",
            )
            .where(
                TaskRecurrenceSeriesModel.series_id.in_(select(owner_series.c.series_id)),
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
            .returning(*self._recurrence_returning_columns())
        )
        result.one()
        await self._set_recurrence_tasks_status_from(
            user_id=user_id,
            recurrence_id=recurrence_id,
            from_datetime=stop_from,
            task_status=TaskStatus.CANCELLED,
        )
        return await self._get_recurrence(user_id, recurrence_id)

    @translate_repository_errors(not_found=app_exc.RecurrenceRuleNotFound)
    async def delete_task_recurrence(self, user_id: UUID, recurrence_id: UUID) -> None:
        now = func.now()
        owner_series = self._owned_recurrence_series(user_id, recurrence_id).cte("owner_series")
        removable_instances = self._removable_recurrence_instances(
            user_id=user_id,
            series_condition=TaskRecurrenceInstanceModel.series_id.in_(
                select(owner_series.c.series_id)
            ),
            cte_name="removable_recurrence_instances",
        )
        deleted_tasks = (
            update(TaskModel)
            .values(deleted_at=now)
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id.in_(select(removable_instances.c.task_id)),
                self._task_is_not_deleted(),
            )
            .returning(TaskModel.task_id)
            .cte("deleted_recurrence_tasks")
        )
        deleted_instances = (
            update(TaskRecurrenceInstanceModel)
            .values(deleted_at=now)
            .where(
                TaskRecurrenceInstanceModel.instance_id.in_(
                    select(removable_instances.c.instance_id)
                ),
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .returning(TaskRecurrenceInstanceModel.instance_id)
            .cte("deleted_recurrence_instances")
        )
        deleted_series = (
            update(TaskRecurrenceSeriesModel)
            .values(deleted_at=now)
            .where(
                TaskRecurrenceSeriesModel.series_id.in_(select(owner_series.c.series_id)),
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
            .returning(TaskRecurrenceSeriesModel.series_id)
            .cte("deleted_recurrence_series")
        )
        result = await self.session.execute(
            select(select(1).select_from(deleted_series).exists())
            .add_cte(deleted_tasks)
            .add_cte(deleted_instances)
        )
        if not result.scalar_one():
            raise app_exc.RecurrenceRuleNotFound

    @translate_repository_errors(not_found=app_exc.RecurrenceRuleNotFound)
    async def recalculate_future_recurrence_instances(
        self,
        user_id: UUID,
        recurrence_id: UUID,
        from_datetime: datetime,
    ) -> None:
        await self._raise_if_recurrence_does_not_belong_to_user(user_id, recurrence_id)
        await self.session.execute(
            text("""
                WITH series_config AS MATERIALIZED (
                    SELECT
                        task_recurrence_series.series_id,
                        task_recurrence_series.frequency::varchar AS frequency,
                        task_recurrence_series.step,
                        task_recurrence_series.anchor_date,
                        task_recurrence_series.default_time,
                        task_recurrence_series.default_duration,
                        task_recurrence_series.repeat_until,
                        task_recurrence_series.max_occurrences,
                        ARRAY(
                            SELECT task_recurrence_weekday.weekday::smallint
                            FROM task_recurrence_weekday
                            WHERE
                                task_recurrence_weekday.series_id
                                    = task_recurrence_series.series_id
                            ORDER BY task_recurrence_weekday.weekday
                        )::smallint[] AS weekdays,
                        task_recurrence_month_rule.month_day,
                        task_recurrence_month_rule.week_of_month,
                        task_recurrence_month_rule.weekday AS month_weekday,
                        task_recurrence_month_rule.business_day_policy::varchar
                            AS business_day_policy,
                        task_recurrence_template.title,
                        task_recurrence_template.description,
                        task_recurrence_template.priority,
                        greatest(
                            1,
                            COALESCE((
                                SELECT max(existing_instance.sequence_no)
                                FROM task_recurrence_instance AS existing_instance
                                WHERE
                                    existing_instance.series_id
                                        = task_recurrence_series.series_id
                                    AND existing_instance.deleted_at IS NULL
                            ), 1)
                        )::integer AS max_sequence_no
                    FROM task_recurrence_series
                    JOIN task_recurrence_template
                        ON task_recurrence_template.template_id = task_recurrence_series.template_id
                    LEFT JOIN task_recurrence_month_rule
                        ON task_recurrence_month_rule.series_id
                            = task_recurrence_series.series_id
                    WHERE
                        task_recurrence_template.creator_id = :user_id
                        AND task_recurrence_template.deleted_at IS NULL
                        AND task_recurrence_series.series_id = :recurrence_id
                        AND task_recurrence_series.deleted_at IS NULL
                ),
                generated_date AS MATERIALIZED (
                    SELECT occurrence.sequence_no, occurrence.planned_date
                    FROM series_config
                    CROSS JOIN LATERAL generate_task_recurrence_dates(
                        series_config.frequency,
                        series_config.step,
                        series_config.anchor_date,
                        series_config.weekdays,
                        series_config.month_day,
                        series_config.week_of_month,
                        series_config.month_weekday,
                        series_config.business_day_policy,
                        series_config.anchor_date,
                        CASE series_config.frequency
                            WHEN 'daily' THEN
                                series_config.anchor_date
                                + (
                                    series_config.step * series_config.max_sequence_no
                                )::integer
                            WHEN 'weekly' THEN
                                series_config.anchor_date
                                + (
                                    7
                                    * series_config.step
                                    * series_config.max_sequence_no
                                )::integer
                            ELSE (
                                series_config.anchor_date
                                + make_interval(
                                    months => (
                                        CASE
                                            WHEN series_config.week_of_month = 5 THEN 4
                                            WHEN series_config.month_day >= 29 THEN 2
                                            ELSE 1
                                        END
                                        * series_config.step
                                        * series_config.max_sequence_no
                                    )::integer
                                )
                            )::date
                        END,
                        NULL,
                        series_config.max_sequence_no
                    ) AS occurrence
                ),
                recalculated AS (
                    SELECT
                        task_recurrence_instance.instance_id,
                        task_recurrence_instance.task_id,
                        series_config.title,
                        series_config.description,
                        series_config.priority,
                        task_recurrence_instance.sequence_no,
                        generated_date.planned_date,
                        series_config.default_time,
                        series_config.default_duration,
                        series_config.repeat_until,
                        series_config.max_occurrences
                    FROM task_recurrence_instance
                    JOIN task
                        ON task.task_id = task_recurrence_instance.task_id
                    JOIN series_config
                        ON series_config.series_id = task_recurrence_instance.series_id
                    JOIN generated_date
                        ON generated_date.sequence_no
                            = task_recurrence_instance.sequence_no
                    WHERE
                        task_recurrence_instance.deleted_at IS NULL
                        AND task_recurrence_instance.is_customized = false
                        AND task_recurrence_instance.planned_starts_at >= :from_datetime
                        AND task.deleted_at IS NULL
                        AND task.status != 'completed'
                ),
                planned AS (
                    SELECT
                        instance_id,
                        task_id,
                        title,
                        description,
                        priority,
                        sequence_no,
                        planned_date,
                        (
                            planned_date::timestamp + default_time
                        ) AS planned_starts_at,
                        (
                            planned_date::timestamp
                            + default_time
                            + COALESCE(default_duration, INTERVAL '0 seconds')
                        ) AS planned_ends_at,
                        default_duration IS NOT NULL AS has_schedule,
                        (
                            (repeat_until IS NULL OR planned_date <= repeat_until)
                            AND (
                                max_occurrences IS NULL
                                OR sequence_no <= max_occurrences
                            )
                        ) AS is_within_rule
                    FROM recalculated
                ),
                updated_instance AS (
                    UPDATE task_recurrence_instance
                    SET
                        planned_date = planned.planned_date,
                        planned_starts_at = planned.planned_starts_at,
                        planned_ends_at = planned.planned_ends_at
                    FROM planned
                    WHERE task_recurrence_instance.instance_id = planned.instance_id
                    RETURNING task_recurrence_instance.task_id
                ),
                updated_task AS (
                    UPDATE task
                    SET
                        title = planned.title,
                        description = planned.description,
                        priority = planned.priority,
                        due_at = planned.planned_ends_at,
                        status = CASE
                            WHEN task.status = 'completed' THEN task.status
                            WHEN NOT planned.is_within_rule THEN 'cancelled'
                            WHEN task.status = 'cancelled' THEN 'active'
                            ELSE task.status
                        END
                    FROM planned
                    WHERE
                        task.task_id = planned.task_id
                        AND task.deleted_at IS NULL
                    RETURNING task.task_id
                ),
                deleted_schedule AS (
                    DELETE FROM scheduled_task
                    USING planned
                    WHERE
                        scheduled_task.task_id = planned.task_id
                        AND NOT planned.has_schedule
                    RETURNING scheduled_task.task_id
                ),
                upserted_schedule AS (
                    INSERT INTO scheduled_task(task_id, starts_at, ends_at)
                    SELECT task_id, planned_starts_at, planned_ends_at
                    FROM planned
                    WHERE has_schedule
                    ON CONFLICT (task_id) DO UPDATE SET
                        starts_at = EXCLUDED.starts_at,
                        ends_at = EXCLUDED.ends_at
                    RETURNING task_id
                )
                SELECT
                    (SELECT count(*) FROM updated_instance) AS updated_instance_count,
                    (SELECT count(*) FROM updated_task) AS updated_task_count,
                    (SELECT count(*) FROM deleted_schedule) AS deleted_schedule_count,
                    (SELECT count(*) FROM upserted_schedule) AS upserted_schedule_count
            """),
            {
                "user_id": user_id,
                "recurrence_id": recurrence_id,
                "from_datetime": from_datetime,
            },
        )

    async def _raise_if_recurrence_schedule_overlaps(
        self,
        *,
        user_id: UUID,
        task_id: UUID | None,
        recurrence_id: UUID | None,
        data: AddTaskRecurrence | UpdateTaskRecurrence,
        current_recurrence: TaskRecurrence | None = None,
    ) -> None:
        if data.default_duration is None:
            return

        if isinstance(data, AddTaskRecurrence):
            frequency = data.frequency
            interval = data.interval
            weekdays = data.weekdays
            month_rule = data.month_rule
        elif current_recurrence is not None:
            frequency = current_recurrence.frequency
            interval = current_recurrence.interval
            weekdays = current_recurrence.weekdays
            month_rule = current_recurrence.month_rule
        else:
            raise ValueError("current recurrence configuration is required")

        stmt = text("""
            WITH generation_bounds AS (
                SELECT
                    CASE
                        WHEN CAST(:repeat_until AS date) IS NOT NULL
                            THEN CAST(:repeat_until AS date)
                        WHEN :frequency = 'daily' THEN
                            CAST(:anchor_date AS date)
                            + (
                                :interval
                                * COALESCE(CAST(:occurrences_limit AS integer), 1000)
                            )::integer
                        WHEN :frequency = 'weekly' THEN
                            CAST(:anchor_date AS date)
                            + (
                                7
                                * :interval
                                * COALESCE(CAST(:occurrences_limit AS integer), 1000)
                            )::integer
                        ELSE (
                            CAST(:anchor_date AS date)
                            + make_interval(
                                months => (
                                    CASE
                                        WHEN CAST(:week_of_month AS integer) = 5 THEN 4
                                        WHEN CAST(:month_day AS integer) >= 29 THEN 2
                                        ELSE 1
                                    END
                                    * :interval
                                    * COALESCE(CAST(:occurrences_limit AS integer), 1000)
                                )::integer
                            )
                        )::date
                    END AS ends_on
            ),
            candidate_occurrence AS MATERIALIZED (
                SELECT
                    occurrence.planned_date::timestamp + CAST(:default_time AS time)
                        AS starts_at,
                    occurrence.planned_date::timestamp
                        + CAST(:default_time AS time)
                        + CAST(:default_duration AS interval) AS ends_at
                FROM generation_bounds
                CROSS JOIN LATERAL generate_task_recurrence_dates(
                    :frequency,
                    :interval,
                    CAST(:anchor_date AS date),
                    CAST(:weekdays AS smallint[]),
                    CAST(:month_day AS integer),
                    CAST(:week_of_month AS integer),
                    CAST(:month_weekday AS integer),
                    :business_day_policy,
                    CAST(:anchor_date AS date),
                    generation_bounds.ends_on,
                    CAST(:repeat_until AS date),
                    CAST(:occurrences_limit AS integer)
                ) AS occurrence
            ),
            ordered_candidate AS (
                SELECT
                    candidate_occurrence.*,
                    max(ends_at) OVER (
                        ORDER BY starts_at, ends_at
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ) AS previous_max_ends_at
                FROM candidate_occurrence
            ),
            existing_overlap AS (
                SELECT 1
                FROM candidate_occurrence
                JOIN scheduled_task
                    ON tsrange(scheduled_task.starts_at, scheduled_task.ends_at, '[)')
                        && tsrange(
                            candidate_occurrence.starts_at,
                            candidate_occurrence.ends_at,
                            '[)'
                        )
                JOIN task ON task.task_id = scheduled_task.task_id
                WHERE
                    task.creator_id = :user_id
                    AND task.deleted_at IS NULL
                    AND task.status != 'cancelled'
                    AND (
                        CAST(:task_id AS uuid) IS NULL
                        OR task.task_id != CAST(:task_id AS uuid)
                    )
                    AND (
                        CAST(:recurrence_id AS uuid) IS NULL
                        OR NOT EXISTS (
                            SELECT 1
                            FROM task_recurrence_instance
                            WHERE
                                task_recurrence_instance.series_id = CAST(:recurrence_id AS uuid)
                                AND task_recurrence_instance.task_id = task.task_id
                                AND task_recurrence_instance.deleted_at IS NULL
                        )
                    )
                LIMIT 1
            ),
            internal_overlap AS (
                SELECT 1
                FROM ordered_candidate
                WHERE starts_at < previous_max_ends_at
                LIMIT 1
            )
            SELECT EXISTS (
                SELECT 1 FROM existing_overlap
                UNION ALL
                SELECT 1 FROM internal_overlap
            ) AS has_overlap
        """)
        weekdays_param = [int(weekday) for weekday in weekdays]
        result = await self.session.execute(
            stmt,
            {
                "user_id": user_id,
                "task_id": task_id,
                "recurrence_id": recurrence_id,
                "frequency": frequency.value,
                "interval": interval,
                "anchor_date": data.anchor_date,
                "default_time": data.default_time,
                "default_duration": data.default_duration,
                "weekdays": weekdays_param,
                "month_day": month_rule.month_day if month_rule is not None else None,
                "week_of_month": month_rule.week_of_month if month_rule is not None else None,
                "month_weekday": (
                    int(month_rule.weekday)
                    if month_rule is not None and month_rule.weekday is not None
                    else None
                ),
                "business_day_policy": (
                    month_rule.business_day_policy.value
                    if month_rule is not None
                    else RecurrenceBusinessDayPolicy.NONE.value
                ),
                "repeat_until": data.repeat_until,
                "occurrences_limit": data.occurrences_limit,
            },
        )
        if result.scalar_one():
            raise app_exc.TaskScheduleOverlap

    async def _raise_if_recurrence_schedules_overlap(
        self,
        *,
        user_id: UUID,
        rules: tuple[AddTaskRecurrence, ...],
    ) -> None:
        stmt = text("""
            WITH rule_input AS MATERIALIZED (
                SELECT
                    row_number() OVER () AS rule_index,
                    rule.frequency,
                    rule.interval,
                    rule.anchor_date,
                    rule.default_time,
                    make_interval(secs => rule.default_duration_seconds) AS default_duration,
                    ARRAY(
                        SELECT weekday.value::smallint
                        FROM jsonb_array_elements_text(rule.weekdays) AS weekday(value)
                        ORDER BY weekday.value::smallint
                    )::smallint[] AS weekdays,
                    (rule.month_rule ->> 'month_day')::integer AS month_day,
                    (rule.month_rule ->> 'week_of_month')::integer AS week_of_month,
                    (rule.month_rule ->> 'weekday')::integer AS month_weekday,
                    COALESCE(
                        rule.month_rule ->> 'business_day_policy',
                        'none'
                    ) AS business_day_policy,
                    rule.repeat_until,
                    rule.occurrences_limit
                FROM jsonb_to_recordset(CAST(:rules AS jsonb)) AS rule(
                    frequency text,
                    interval integer,
                    anchor_date date,
                    default_time time,
                    default_duration_seconds double precision,
                    weekdays jsonb,
                    month_rule jsonb,
                    repeat_until date,
                    occurrences_limit integer
                )
                WHERE rule.default_duration_seconds IS NOT NULL
            ),
            candidate_occurrence AS MATERIALIZED (
                SELECT
                    rule_input.rule_index,
                    occurrence.planned_date::timestamp + rule_input.default_time AS starts_at,
                    occurrence.planned_date::timestamp
                        + rule_input.default_time
                        + rule_input.default_duration AS ends_at
                FROM rule_input
                CROSS JOIN LATERAL generate_task_recurrence_dates(
                    rule_input.frequency,
                    rule_input.interval,
                    rule_input.anchor_date,
                    rule_input.weekdays,
                    rule_input.month_day,
                    rule_input.week_of_month,
                    rule_input.month_weekday,
                    rule_input.business_day_policy,
                    rule_input.anchor_date,
                    CASE
                        WHEN rule_input.repeat_until IS NOT NULL
                            THEN rule_input.repeat_until
                        WHEN rule_input.frequency = 'daily' THEN
                            rule_input.anchor_date
                            + (
                                rule_input.interval
                                * COALESCE(rule_input.occurrences_limit, 1000)
                            )::integer
                        WHEN rule_input.frequency = 'weekly' THEN
                            rule_input.anchor_date
                            + (
                                7
                                * rule_input.interval
                                * COALESCE(rule_input.occurrences_limit, 1000)
                            )::integer
                        ELSE (
                            rule_input.anchor_date
                            + make_interval(
                                months => (
                                    CASE
                                        WHEN rule_input.week_of_month = 5 THEN 4
                                        WHEN rule_input.month_day >= 29 THEN 2
                                        ELSE 1
                                    END
                                    * rule_input.interval
                                    * COALESCE(rule_input.occurrences_limit, 1000)
                                )::integer
                            )
                        )::date
                    END,
                    rule_input.repeat_until,
                    rule_input.occurrences_limit
                ) AS occurrence
            ),
            bounded_candidate AS MATERIALIZED (
                SELECT rule_index, starts_at, ends_at
                FROM candidate_occurrence
            ),
            ordered_candidate AS (
                SELECT
                    bounded_candidate.*,
                    max(ends_at) OVER (
                        ORDER BY starts_at, ends_at
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ) AS previous_max_ends_at
                FROM bounded_candidate
            ),
            existing_overlap AS (
                SELECT 1
                FROM bounded_candidate
                JOIN scheduled_task
                    ON tsrange(scheduled_task.starts_at, scheduled_task.ends_at, '[)')
                        && tsrange(
                            bounded_candidate.starts_at,
                            bounded_candidate.ends_at,
                            '[)'
                        )
                JOIN task ON task.task_id = scheduled_task.task_id
                WHERE
                    task.creator_id = :user_id
                    AND task.deleted_at IS NULL
                    AND task.status != 'cancelled'
                LIMIT 1
            ),
            internal_overlap AS (
                SELECT 1
                FROM ordered_candidate
                WHERE starts_at < previous_max_ends_at
                LIMIT 1
            )
            SELECT EXISTS (
                SELECT 1 FROM existing_overlap
                UNION ALL
                SELECT 1 FROM internal_overlap
            ) AS has_overlap
        """)
        result = await self.session.execute(
            stmt,
            {
                "user_id": user_id,
                "rules": self._recurrence_rules_json(rules),
            },
        )
        if result.scalar_one():
            raise app_exc.TaskScheduleOverlap

    async def _get_recurrence(self, user_id: UUID, recurrence_id: UUID) -> TaskRecurrence:
        stmt = (
            select(TaskRecurrenceSeriesModel)
            .options(
                selectinload(TaskRecurrenceSeriesModel.weekdays),
                selectinload(TaskRecurrenceSeriesModel.month_rule),
            )
            .join(
                TaskRecurrenceTemplateModel,
                TaskRecurrenceTemplateModel.template_id == TaskRecurrenceSeriesModel.template_id,
            )
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                TaskRecurrenceSeriesModel.series_id == recurrence_id,
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return self._model_to_recurrence(result.scalar_one())

    async def _set_recurrence_tasks_status_from(
        self,
        *,
        user_id: UUID,
        recurrence_id: UUID,
        from_datetime: datetime,
        task_status: TaskStatus,
    ) -> None:
        task_ids = self._task_ids_for_recurrence_from(recurrence_id, from_datetime)
        await self.session.execute(
            update(TaskModel)
            .values(status=task_status)
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id.in_(task_ids),
                self._task_is_not_deleted(),
            )
        )

    @classmethod
    def _removable_recurrence_instances(
        cls,
        *,
        user_id: UUID,
        series_condition: ColumnElement[bool],
        cte_name: str,
    ) -> CTE:
        return (
            select(
                TaskRecurrenceInstanceModel.instance_id,
                TaskRecurrenceInstanceModel.task_id,
            )
            .join(TaskModel, TaskModel.task_id == TaskRecurrenceInstanceModel.task_id)
            .where(
                series_condition,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
                TaskModel.creator_id == user_id,
                TaskModel.status != TaskStatus.COMPLETED,
                cls._task_is_not_deleted(),
            )
            .cte(cte_name)
        )

    @staticmethod
    def _task_ids_for_recurrence(recurrence_id: UUID):
        return select(TaskRecurrenceInstanceModel.task_id).where(
            TaskRecurrenceInstanceModel.series_id == recurrence_id,
            TaskRecurrenceInstanceModel.deleted_at.is_(None),
        )

    @staticmethod
    def _task_ids_for_recurrence_from(recurrence_id: UUID, from_datetime: datetime):
        return select(TaskRecurrenceInstanceModel.task_id).where(
            TaskRecurrenceInstanceModel.series_id == recurrence_id,
            TaskRecurrenceInstanceModel.planned_starts_at >= from_datetime,
            TaskRecurrenceInstanceModel.deleted_at.is_(None),
        )

    async def _raise_if_recurrence_does_not_belong_to_user(
        self,
        user_id: UUID,
        recurrence_id: UUID,
    ) -> None:
        stmt = select(self._owned_recurrence_series(user_id, recurrence_id).exists())
        result = await self.session.execute(stmt)
        if not result.scalar_one():
            raise app_exc.RecurrenceRuleNotFound

    @staticmethod
    def _owned_recurrence_series(user_id: UUID, recurrence_id: UUID):
        return (
            select(TaskRecurrenceSeriesModel.series_id)
            .join(
                TaskRecurrenceTemplateModel,
                TaskRecurrenceTemplateModel.template_id == TaskRecurrenceSeriesModel.template_id,
            )
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                TaskRecurrenceSeriesModel.series_id == recurrence_id,
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
        )

    @staticmethod
    def _owned_recurrence_template(user_id: UUID, template_id: UUID):
        return select(TaskRecurrenceTemplateModel.template_id).where(
            TaskRecurrenceTemplateModel.creator_id == user_id,
            TaskRecurrenceTemplateModel.template_id == template_id,
            TaskRecurrenceTemplateModel.deleted_at.is_(None),
        )

    async def _sync_recurrence_template_tag(
        self,
        *,
        user_id: UUID,
        template_id: UUID,
        tag_id: UUID,
        action: Literal["add", "delete"],
    ) -> None:
        if action == "add":
            stmt = self._add_recurrence_template_tag_stmt()
        elif action == "delete":
            stmt = self._delete_recurrence_template_tag_stmt()
        else:
            raise ValueError("unsupported recurrence template tag action")

        result = await self.session.execute(
            stmt,
            {"user_id": user_id, "template_id": template_id, "tag_id": tag_id},
        )
        row = result.one()
        if not row.template_exists:
            raise app_exc.RecurrenceTemplateNotFound
        if not row.tag_exists:
            raise app_exc.TagNotFound

    @staticmethod
    def _add_recurrence_template_tag_stmt():
        return text("""
            WITH owner_template AS MATERIALIZED (
                SELECT template_id
                FROM task_recurrence_template
                WHERE
                    creator_id = :user_id
                    AND template_id = :template_id
                    AND deleted_at IS NULL
            ),
            owned_tag AS MATERIALIZED (
                SELECT tag_id
                FROM tag
                WHERE
                    creator_id = :user_id
                    AND tag_id = :tag_id
                    AND deleted_at IS NULL
            ),
            inserted_template_tag AS (
                INSERT INTO task_recurrence_template_tag(template_id, tag_id)
                SELECT owner_template.template_id, owned_tag.tag_id
                FROM owner_template
                CROSS JOIN owned_tag
                ON CONFLICT (template_id, tag_id) DO NOTHING
                RETURNING template_id
            ),
            current_active_instance_task AS MATERIALIZED (
                SELECT task_recurrence_instance.task_id
                FROM owner_template
                JOIN task_recurrence_series
                    ON task_recurrence_series.template_id = owner_template.template_id
                JOIN task_recurrence_instance
                    ON task_recurrence_instance.series_id = task_recurrence_series.series_id
                JOIN task
                    ON task.task_id = task_recurrence_instance.task_id
                WHERE
                    task_recurrence_series.deleted_at IS NULL
                    AND task_recurrence_instance.deleted_at IS NULL
                    AND task_recurrence_instance.planned_ends_at >= localtimestamp
                    AND task.creator_id = :user_id
                    AND task.deleted_at IS NULL
                    AND task.status = 'active'
            ),
            inserted_task_tag AS (
                INSERT INTO task_tag(task_id, tag_id)
                SELECT current_active_instance_task.task_id, owned_tag.tag_id
                FROM current_active_instance_task
                CROSS JOIN owned_tag
                ON CONFLICT (task_id, tag_id) DO NOTHING
                RETURNING task_id
            )
            SELECT
                EXISTS (SELECT 1 FROM owner_template) AS template_exists,
                EXISTS (SELECT 1 FROM owned_tag) AS tag_exists
        """)

    @staticmethod
    def _delete_recurrence_template_tag_stmt():
        return text("""
            WITH owner_template AS MATERIALIZED (
                SELECT template_id
                FROM task_recurrence_template
                WHERE
                    creator_id = :user_id
                    AND template_id = :template_id
                    AND deleted_at IS NULL
            ),
            owned_tag AS MATERIALIZED (
                SELECT tag_id
                FROM tag
                WHERE
                    creator_id = :user_id
                    AND tag_id = :tag_id
                    AND deleted_at IS NULL
            ),
            deleted_template_tag AS (
                DELETE FROM task_recurrence_template_tag
                USING owner_template, owned_tag
                WHERE
                    task_recurrence_template_tag.template_id = owner_template.template_id
                    AND task_recurrence_template_tag.tag_id = owned_tag.tag_id
                RETURNING task_recurrence_template_tag.template_id
            ),
            current_active_instance_task AS MATERIALIZED (
                SELECT task_recurrence_instance.task_id
                FROM owner_template
                JOIN task_recurrence_series
                    ON task_recurrence_series.template_id = owner_template.template_id
                JOIN task_recurrence_instance
                    ON task_recurrence_instance.series_id = task_recurrence_series.series_id
                JOIN task
                    ON task.task_id = task_recurrence_instance.task_id
                WHERE
                    task_recurrence_series.deleted_at IS NULL
                    AND task_recurrence_instance.deleted_at IS NULL
                    AND task_recurrence_instance.planned_ends_at >= localtimestamp
                    AND task.creator_id = :user_id
                    AND task.deleted_at IS NULL
                    AND task.status = 'active'
            ),
            deleted_task_tag AS (
                DELETE FROM task_tag
                USING current_active_instance_task, owned_tag
                WHERE
                    task_tag.task_id = current_active_instance_task.task_id
                    AND task_tag.tag_id = owned_tag.tag_id
                RETURNING task_tag.task_id
            )
            SELECT
                EXISTS (SELECT 1 FROM owner_template) AS template_exists,
                EXISTS (SELECT 1 FROM owned_tag) AS tag_exists
        """)

    @classmethod
    def _select_recurrence_template_rows(cls, template_page):
        weekdays = (
            select(
                func.array_agg(
                    aggregate_order_by(
                        TaskRecurrenceWeekdayModel.weekday,
                        TaskRecurrenceWeekdayModel.weekday,
                    )
                )
            )
            .where(TaskRecurrenceWeekdayModel.series_id == TaskRecurrenceSeriesModel.series_id)
            .correlate(TaskRecurrenceSeriesModel)
            .scalar_subquery()
            .label("weekdays")
        )
        return (
            select(
                TaskRecurrenceTemplateModel.template_id,
                TaskRecurrenceTemplateModel.title,
                TaskRecurrenceTemplateModel.description,
                TaskRecurrenceTemplateModel.priority,
                TaskRecurrenceTemplateModel.created_at,
                TagModel.tag_id.label("tag_id"),
                TagModel.name.label("tag_name"),
                TagModel.created_at.label("tag_created_at"),
                *cls._recurrence_returning_columns(),
                weekdays,
                TaskRecurrenceMonthRuleModel.month_day,
                TaskRecurrenceMonthRuleModel.week_of_month,
                TaskRecurrenceMonthRuleModel.weekday.label("month_weekday"),
                TaskRecurrenceMonthRuleModel.business_day_policy,
            )
            .select_from(TaskRecurrenceTemplateModel)
            .join(
                template_page,
                template_page.c.template_id == TaskRecurrenceTemplateModel.template_id,
            )
            .outerjoin(
                TaskRecurrenceSeriesModel,
                (TaskRecurrenceSeriesModel.template_id == TaskRecurrenceTemplateModel.template_id)
                & (TaskRecurrenceSeriesModel.deleted_at.is_(None)),
            )
            .outerjoin(
                TaskRecurrenceMonthRuleModel,
                TaskRecurrenceMonthRuleModel.series_id == TaskRecurrenceSeriesModel.series_id,
            )
            .outerjoin(
                TaskRecurrenceTemplateTagModel,
                TaskRecurrenceTemplateTagModel.template_id
                == TaskRecurrenceTemplateModel.template_id,
            )
            .outerjoin(
                TagModel,
                (TagModel.tag_id == TaskRecurrenceTemplateTagModel.tag_id)
                & (TagModel.deleted_at.is_(None)),
            )
            .order_by(
                TaskRecurrenceTemplateModel.created_at.desc(),
                TaskRecurrenceTemplateModel.template_id.desc(),
                TagModel.name,
                TaskRecurrenceSeriesModel.anchor_date,
                TaskRecurrenceSeriesModel.default_time,
            )
        )

    @classmethod
    def _insert_recurrence_series_for_template(cls, owner_template, data: AddTaskRecurrence):
        end_mode = recurrence_end_mode(
            repeat_until=data.repeat_until,
            max_occurrences=data.occurrences_limit,
        )
        recurrence_values = select(
            owner_template.c.template_id,
            sql_cast(literal(data.frequency.value), TaskRecurrenceSeriesModel.frequency.type),
            literal(data.interval),
            sql_cast(literal(data.anchor_date), TaskRecurrenceSeriesModel.anchor_date.type),
            sql_cast(literal(data.default_time), TaskRecurrenceSeriesModel.default_time.type),
            sql_cast(
                literal(data.default_duration),
                TaskRecurrenceSeriesModel.default_duration.type,
            ),
            sql_cast(literal(end_mode.value), TaskRecurrenceSeriesModel.end_mode.type),
            sql_cast(
                literal(data.repeat_until),
                TaskRecurrenceSeriesModel.repeat_until.type,
            ),
            literal(data.occurrences_limit),
        ).select_from(owner_template)
        return (
            insert(TaskRecurrenceSeriesModel)
            .from_select(
                (
                    "template_id",
                    "frequency",
                    "step",
                    "anchor_date",
                    "default_time",
                    "default_duration",
                    "end_mode",
                    "repeat_until",
                    "max_occurrences",
                ),
                recurrence_values,
            )
            .returning(*cls._recurrence_returning_columns())
            .cte("inserted_series")
        )

    @staticmethod
    def _insert_recurrence_weekdays(inserted_series, data: AddTaskRecurrence):
        if data.weekdays:
            weekday_values = union_all(
                *(
                    select(inserted_series.c.series_id, literal(int(weekday)))
                    for weekday in data.weekdays
                )
            )
        else:
            weekday_values = select(inserted_series.c.series_id, literal(0)).where(literal(False))
        return (
            pg_insert(TaskRecurrenceWeekdayModel)
            .from_select(
                ("series_id", "weekday"),
                weekday_values,
            )
            .on_conflict_do_nothing(index_elements=["series_id", "weekday"])
            .returning(TaskRecurrenceWeekdayModel.series_id)
            .cte("inserted_weekday")
        )

    @staticmethod
    def _insert_recurrence_month_rule(inserted_series, data: AddTaskRecurrence):
        month_rule = data.month_rule
        month_values = select(
            inserted_series.c.series_id,
            literal(month_rule.month_day if month_rule is not None else None),
            literal(month_rule.week_of_month if month_rule is not None else None),
            literal(
                int(month_rule.weekday)
                if month_rule is not None and month_rule.weekday is not None
                else None
            ),
            sql_cast(
                literal(
                    month_rule.business_day_policy.value
                    if month_rule is not None
                    else RecurrenceBusinessDayPolicy.NONE.value
                ),
                TaskRecurrenceMonthRuleModel.business_day_policy.type,
            ),
        )
        if month_rule is None:
            month_values = month_values.where(literal(False))
        return (
            pg_insert(TaskRecurrenceMonthRuleModel)
            .from_select(
                (
                    "series_id",
                    "month_day",
                    "week_of_month",
                    "weekday",
                    "business_day_policy",
                ),
                month_values,
            )
            .on_conflict_do_nothing(index_elements=["series_id"])
            .returning(TaskRecurrenceMonthRuleModel.series_id)
            .cte("inserted_month_rule")
        )

    @staticmethod
    def _recurrence_columns_from(series):
        return (
            series.c.series_id,
            series.c.template_id,
            series.c.frequency,
            series.c.step,
            series.c.anchor_date,
            series.c.default_time,
            series.c.default_duration,
            series.c.repeat_until,
            series.c.max_occurrences,
        )

    async def _raise_if_recurrence_template_does_not_belong_to_user(
        self,
        user_id: UUID,
        template_id: UUID,
    ) -> None:
        stmt = select(
            select(1)
            .select_from(TaskRecurrenceTemplateModel)
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.template_id == template_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
            )
            .exists()
        )
        result = await self.session.execute(stmt)
        if not result.scalar_one():
            raise app_exc.RecurrenceTemplateNotFound
