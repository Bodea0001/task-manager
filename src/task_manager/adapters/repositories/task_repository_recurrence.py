from uuid import UUID
from datetime import datetime, time, timedelta

from sqlalchemy import (
    text,
    func,
    cast as sql_cast,
    select,
    insert,
    update,
    delete,
    literal,
    bindparam,
)
from sqlalchemy.types import Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert

import exceptions as app_exc
from config import settings
from dto.tasks import (
    AddTaskRecurrence,
    AddTaskRecurrenceTemplate,
    UpdateTaskRecurrence,
    ListTaskRecurrenceTemplatesFilters,
)
from models.tasks import (
    Task as TaskModel,
    TaskRecurrenceSeries as TaskRecurrenceSeriesModel,
    TaskRecurrenceWeekday as TaskRecurrenceWeekdayModel,
    TaskRecurrenceTemplate as TaskRecurrenceTemplateModel,
    TaskRecurrenceInstance as TaskRecurrenceInstanceModel,
    TaskRecurrenceMonthRule as TaskRecurrenceMonthRuleModel,
)
from domain.recurrences import recurrence_end_mode
from domain.value_objects.tasks import (
    Schedule,
    TaskStatus,
    TaskRecurrence,
    RecurrenceEndMode,
    RecurrenceFrequency,
    RecurrenceSkipPolicy,
    TaskRecurrenceTemplate,
    RecurrenceCalculationMode,
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
        if not windows:
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
                    task_recurrence_template.title,
                    task_recurrence_template.description,
                    task_recurrence_template.priority,
                    task_recurrence_template.creator_id,
                    requested_window.starts_on,
                    requested_window.ends_on,
                    greatest(
                        1,
                        CASE task_recurrence_series.frequency::varchar
                            WHEN 'daily' THEN (
                                ((requested_window.starts_on
                                    - task_recurrence_series.anchor_date)
                                    / task_recurrence_series.step)
                                + 1
                            )
                            WHEN 'weekly' THEN (
                                ((requested_window.starts_on
                                    - task_recurrence_series.anchor_date)
                                    / (7 * task_recurrence_series.step))
                                + 1
                            )
                            ELSE (
                                (
                                    (
                                        (date_part('year', requested_window.starts_on)::int
                                            - date_part(
                                                'year',
                                                task_recurrence_series.anchor_date
                                            )::int
                                        ) * 12
                                    )
                                    + date_part('month', requested_window.starts_on)::int
                                    - date_part(
                                        'month',
                                        task_recurrence_series.anchor_date
                                    )::int
                                ) / task_recurrence_series.step
                            ) + 1
                        END
                    )::int AS first_sequence_no,
                    least(
                        COALESCE(task_recurrence_series.max_occurrences, 2147483647),
                        greatest(
                            1,
                            CASE task_recurrence_series.frequency::varchar
                                WHEN 'daily' THEN (
                                    (
                                        least(
                                            requested_window.ends_on,
                                            COALESCE(
                                                task_recurrence_series.repeat_until,
                                                requested_window.ends_on
                                            )
                                        )
                                        - task_recurrence_series.anchor_date
                                    )
                                    / task_recurrence_series.step
                                ) + 1
                                WHEN 'weekly' THEN (
                                    (
                                        least(
                                            requested_window.ends_on,
                                            COALESCE(
                                                task_recurrence_series.repeat_until,
                                                requested_window.ends_on
                                            )
                                        )
                                        - task_recurrence_series.anchor_date
                                    )
                                    / (7 * task_recurrence_series.step)
                                ) + 1
                                ELSE (
                                    (
                                        (
                                            (
                                                date_part(
                                                    'year',
                                                    least(
                                                        requested_window.ends_on,
                                                        COALESCE(
                                                            task_recurrence_series.repeat_until,
                                                            requested_window.ends_on
                                                        )
                                                    )
                                                )::int
                                                - date_part(
                                                    'year',
                                                    task_recurrence_series.anchor_date
                                                )::int
                                            ) * 12
                                        )
                                        + date_part(
                                            'month',
                                            least(
                                                requested_window.ends_on,
                                                COALESCE(
                                                    task_recurrence_series.repeat_until,
                                                    requested_window.ends_on
                                                )
                                            )
                                        )::int
                                        - date_part(
                                            'month',
                                            task_recurrence_series.anchor_date
                                        )::int
                                    ) / task_recurrence_series.step
                                ) + 1
                            END
                        )
                    )::int AS last_sequence_no
                FROM task_recurrence_series
                JOIN task_recurrence_template
                    ON task_recurrence_template.template_id = task_recurrence_series.template_id
                JOIN requested_window
                    ON requested_window.frequency = task_recurrence_series.frequency::varchar
                    AND requested_window.ends_on >= task_recurrence_series.anchor_date
                WHERE
                    task_recurrence_template.creator_id = :user_id
                    AND task_recurrence_template.deleted_at IS NULL
                    AND task_recurrence_series.deleted_at IS NULL
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
                        occurrence.planned_date::timestamp
                        + COALESCE(series_window.default_time, TIME '00:00')
                    ) AS planned_starts_at,
                    COALESCE(
                        occurrence_override.override_ends_at,
                        occurrence.planned_date::timestamp
                        + COALESCE(series_window.default_time, TIME '00:00')
                        + COALESCE(series_window.default_duration, INTERVAL '0 seconds')
                    ) AS planned_ends_at,
                    series_window.ends_on
                FROM series_window
                CROSS JOIN LATERAL (
                    SELECT
                        sequence_no,
                        CASE series_window.frequency
                            WHEN 'daily' THEN (
                                series_window.anchor_date
                                + ((sequence_no - 1) * series_window.step)
                            )
                            WHEN 'weekly' THEN (
                                series_window.anchor_date
                                + ((sequence_no - 1) * series_window.step * 7)
                            )
                            ELSE (
                                series_window.anchor_date
                                + make_interval(
                                    months => ((sequence_no - 1) * series_window.step)::int
                                )
                            )::date
                        END AS planned_date
                    FROM generate_series(
                        series_window.first_sequence_no,
                        series_window.last_sequence_no
                    ) AS generated(sequence_no)
                ) AS occurrence
                LEFT JOIN task_recurrence_instance_override AS occurrence_override
                    ON occurrence_override.series_id = series_window.series_id
                    AND occurrence_override.planned_starts_at = (
                        occurrence.planned_date::timestamp
                        + COALESCE(series_window.default_time, TIME '00:00')
                    )
                    AND occurrence_override.deleted_at IS NULL
                WHERE
                    occurrence.planned_date >= series_window.starts_on
                    AND occurrence.planned_date <= series_window.ends_on
                    AND (
                        occurrence_override.action IS NULL
                        OR occurrence_override.action NOT IN ('skip', 'delete')
                    )
                    AND (
                        series_window.repeat_until IS NULL
                        OR occurrence.planned_date <= series_window.repeat_until
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
            conflict_candidate AS MATERIALIZED (
                SELECT
                    candidate.*,
                    EXISTS (
                        SELECT 1
                        FROM scheduled_task
                        JOIN task ON task.task_id = scheduled_task.task_id
                        WHERE
                            task.creator_id = candidate.creator_id
                            AND task.deleted_at IS NULL
                            AND task.status != 'cancelled'
                            AND scheduled_task.starts_at < candidate.planned_ends_at
                            AND scheduled_task.ends_at > candidate.planned_starts_at
                    ) AS has_schedule_conflict
                FROM candidate
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
                    conflict_candidate.planned_ends_at
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
                SELECT NULL::uuid AS task_id WHERE false
            )
            SELECT
                (SELECT count(*) FROM inserted_instance) AS inserted_count,
                (SELECT count(*) FROM inserted_conflict) AS conflict_count,
                (SELECT count(*) FROM resolved_conflict) AS resolved_conflict_count
        """).bindparams(
            bindparam("window_starts", type_=ARRAY(TIMESTAMP(timezone=False))),
            bindparam("window_ends", type_=ARRAY(TIMESTAMP(timezone=False))),
        )

        await self.session.execute(
            stmt,
            {
                "user_id": user_id,
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
        stmt = text("""
            WITH rule_input AS MATERIALIZED (
                SELECT
                    row_number() OVER () AS rule_index,
                    rule.frequency,
                    rule.interval,
                    rule.starts_at,
                    rule.ends_at,
                    rule.repeat_until,
                    rule.occurrences_limit
                FROM jsonb_to_recordset(CAST(:rules AS jsonb)) AS rule(
                    frequency text,
                    interval integer,
                    starts_at timestamp,
                    ends_at timestamp,
                    repeat_until timestamp,
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
            inserted_series AS (
                INSERT INTO task_recurrence_series(
                    template_id,
                    frequency,
                    step,
                    anchor_date,
                    default_time,
                    default_duration,
                    calculation_mode,
                    skip_policy,
                    end_mode,
                    repeat_until,
                    max_occurrences
                )
                SELECT
                    inserted_template.template_id,
                    rule_input.frequency::recurrencefrequency,
                    rule_input.interval,
                    rule_input.starts_at::date,
                    rule_input.starts_at::time,
                    rule_input.ends_at - rule_input.starts_at,
                    'scheduled_date'::recurrencecalculationmode,
                    'allow_overdue'::recurrenceskippolicy,
                    CASE
                        WHEN rule_input.repeat_until IS NOT NULL THEN 'until_date'
                        WHEN rule_input.occurrences_limit IS NOT NULL THEN 'count'
                        ELSE 'never'
                    END::recurrenceendmode,
                    rule_input.repeat_until::date,
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
                    extract(isodow FROM inserted_series.anchor_date)::int
                FROM inserted_series
                WHERE inserted_series.frequency = 'weekly'
                ON CONFLICT (series_id, weekday) DO NOTHING
                RETURNING series_id
            ),
            inserted_month_rule AS (
                INSERT INTO task_recurrence_month_rule(
                    series_id,
                    month_day,
                    business_day_policy
                )
                SELECT
                    inserted_series.series_id,
                    extract(day FROM inserted_series.anchor_date)::int,
                    'none'::recurrencebusinessdaypolicy
                FROM inserted_series
                WHERE inserted_series.frequency = 'monthly'
                ON CONFLICT (series_id) DO NOTHING
                RETURNING series_id
            )
            SELECT
                inserted_template.template_id,
                inserted_template.title,
                inserted_template.description,
                inserted_template.priority,
                inserted_template.created_at,
                inserted_series.series_id,
                inserted_series.frequency,
                inserted_series.step,
                inserted_series.anchor_date,
                inserted_series.default_time,
                inserted_series.default_duration,
                inserted_series.repeat_until,
                inserted_series.max_occurrences
            FROM inserted_template
            JOIN inserted_series ON inserted_series.template_id = inserted_template.template_id
            ORDER BY inserted_series.anchor_date, inserted_series.default_time
        """)
        result = await self.session.execute(
            stmt,
            {
                "user_id": user_id,
                "title": data.title,
                "description": data.description,
                "priority": data.priority.value,
                "rules": self._recurrence_rules_json(data.rules),
            },
        )
        rows = result.all()
        template = self._rows_to_recurrence_template(rows)
        await self.materialize_recurrence_instances(
            user_id,
            tuple(self._initial_materialization_window(rule) for rule in data.rules),
        )
        return template

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
            raise app_exc.TaskNotFound
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

    @translate_repository_errors
    async def add_task_recurrence_rule(
        self, user_id: UUID, template_id: UUID, data: AddTaskRecurrence
    ) -> TaskRecurrence:
        await self._raise_if_recurrence_schedule_overlaps(
            user_id=user_id, task_id=None, recurrence_id=None, data=data
        )
        inserted_series = self._insert_recurrence_series_for_template(
            self._owned_recurrence_template(user_id, template_id).cte("owner_template"),
            data,
        )
        inserted_weekday = self._insert_recurrence_weekday_from_series(inserted_series)
        inserted_month_rule = self._insert_recurrence_month_rule_from_series(inserted_series)
        stmt = (
            select(*self._recurrence_columns_from(inserted_series))
            .add_cte(inserted_weekday)
            .add_cte(inserted_month_rule)
        )
        result = await self.session.execute(stmt)
        recurrence = self._row_to_recurrence(result.one())
        await self.materialize_recurrence_instances(
            user_id,
            (self._initial_materialization_window(data),),
        )
        return recurrence

    async def get_task_recurrence_rules(
        self, user_id: UUID, template_id: UUID
    ) -> list[TaskRecurrence]:
        stmt = (
            select(TaskRecurrenceSeriesModel)
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

    @translate_repository_errors
    async def get_recurrence(self, user_id: UUID, recurrence_id: UUID) -> TaskRecurrence:
        return await self._get_recurrence(user_id, recurrence_id)

    @translate_repository_errors
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
        max_sequence_no = (
            select(func.max(TaskRecurrenceInstanceModel.sequence_no))
            .where(
                TaskRecurrenceInstanceModel.series_id == TaskRecurrenceSeriesModel.series_id,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .correlate(TaskRecurrenceSeriesModel)
            .scalar_subquery()
        )
        max_planned_starts_at = (
            select(func.max(TaskRecurrenceInstanceModel.planned_starts_at))
            .where(
                TaskRecurrenceInstanceModel.series_id == TaskRecurrenceSeriesModel.series_id,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .correlate(TaskRecurrenceSeriesModel)
            .scalar_subquery()
        )
        stmt = (
            select(TaskRecurrenceTemplateModel.creator_id)
            .join(
                TaskRecurrenceSeriesModel,
                TaskRecurrenceSeriesModel.template_id == TaskRecurrenceTemplateModel.template_id,
            )
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
                        func.coalesce(max_sequence_no, 0)
                        < TaskRecurrenceSeriesModel.max_occurrences
                    )
                ),
                (max_planned_starts_at.is_(None) | (max_planned_starts_at < window.ends_at)),
            )
            .distinct()
            .order_by(TaskRecurrenceTemplateModel.creator_id)
        )
        result = await self.session.execute(stmt)
        return tuple(result.scalars())

    @translate_repository_errors
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
            frequency=current_recurrence.frequency,
            interval=current_recurrence.interval,
        )

        result = await self.session.execute(
            update(TaskRecurrenceSeriesModel)
            .values(
                **self._recurrence_update_values(
                    data,
                    frequency=current_recurrence.frequency,
                    interval=current_recurrence.interval,
                )
            )
            .where(
                TaskRecurrenceSeriesModel.series_id == recurrence_id,
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
            .returning(*self._recurrence_returning_columns())
        )
        recurrence = self._row_to_recurrence(result.one())
        await self._replace_recurrence_rule(recurrence_id, data, recurrence.frequency)
        await self.recalculate_future_recurrence_instances(
            user_id=user_id,
            recurrence_id=recurrence_id,
            from_datetime=datetime.combine(data.schedule.starts_at.date(), time.min),
        )
        await self.materialize_recurrence_instances(
            user_id, (self._initial_materialization_window(data, frequency=recurrence.frequency),)
        )
        return recurrence

    @translate_repository_errors
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
        row = result.one_or_none()
        if row is None:
            raise app_exc.TaskNotFound

        await self._set_recurrence_tasks_status_from(
            user_id=user_id,
            recurrence_id=recurrence_id,
            from_datetime=stop_from,
            task_status=TaskStatus.CANCELLED,
        )
        return self._row_to_recurrence(row)

    @translate_repository_errors
    async def delete_task_recurrence(self, user_id: UUID, recurrence_id: UUID) -> None:
        now = func.now()
        owner_series = self._owned_recurrence_series(user_id, recurrence_id).cte("owner_series")
        task_ids = select(TaskRecurrenceInstanceModel.task_id).where(
            TaskRecurrenceInstanceModel.series_id.in_(select(owner_series.c.series_id)),
            TaskRecurrenceInstanceModel.deleted_at.is_(None),
        )
        deleted_tasks = (
            update(TaskModel)
            .values(deleted_at=now)
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id.in_(task_ids),
                self._task_is_not_deleted(),
            )
            .returning(TaskModel.task_id)
            .cte("deleted_recurrence_tasks")
        )
        deleted_instances = (
            update(TaskRecurrenceInstanceModel)
            .values(deleted_at=now)
            .where(
                TaskRecurrenceInstanceModel.series_id.in_(select(owner_series.c.series_id)),
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
            raise app_exc.TaskNotFound

    @translate_repository_errors
    async def recalculate_future_recurrence_instances(
        self,
        user_id: UUID,
        recurrence_id: UUID,
        from_datetime: datetime,
    ) -> None:
        await self._raise_if_recurrence_does_not_belong_to_user(user_id, recurrence_id)
        await self.session.execute(
            text("""
                WITH recalculated AS (
                    SELECT
                        task_recurrence_instance.instance_id,
                        task_recurrence_instance.task_id,
                        task_recurrence_template.title,
                        task_recurrence_template.description,
                        task_recurrence_template.priority,
                        task_recurrence_instance.sequence_no,
                        CASE task_recurrence_series.frequency::varchar
                            WHEN 'daily' THEN (
                                task_recurrence_series.anchor_date
                                + ((task_recurrence_instance.sequence_no - 1)
                                    * task_recurrence_series.step)
                            )
                            WHEN 'weekly' THEN (
                                task_recurrence_series.anchor_date
                                + ((task_recurrence_instance.sequence_no - 1)
                                    * task_recurrence_series.step * 7)
                            )
                            ELSE (
                                task_recurrence_series.anchor_date
                                + make_interval(
                                    months => (
                                        (task_recurrence_instance.sequence_no - 1)
                                        * task_recurrence_series.step
                                    )::int
                                )
                            )::date
                        END AS planned_date,
                        task_recurrence_series.default_time,
                        task_recurrence_series.default_duration
                    FROM task_recurrence_instance
                    JOIN task_recurrence_series
                        ON task_recurrence_series.series_id = task_recurrence_instance.series_id
                    JOIN task_recurrence_template
                        ON task_recurrence_template.template_id = task_recurrence_series.template_id
                    WHERE
                        task_recurrence_template.creator_id = :user_id
                        AND task_recurrence_template.deleted_at IS NULL
                        AND task_recurrence_series.series_id = :recurrence_id
                        AND task_recurrence_series.deleted_at IS NULL
                        AND task_recurrence_instance.deleted_at IS NULL
                        AND task_recurrence_instance.is_customized = false
                        AND task_recurrence_instance.planned_starts_at >= :from_datetime
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
                            planned_date::timestamp
                            + COALESCE(default_time, TIME '00:00')
                        ) AS planned_starts_at,
                        (
                            planned_date::timestamp
                            + COALESCE(default_time, TIME '00:00')
                            + COALESCE(default_duration, INTERVAL '0 seconds')
                        ) AS planned_ends_at
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
                            WHEN task.status = 'cancelled' THEN 'active'
                            ELSE task.status
                        END
                    FROM planned
                    WHERE
                        task.task_id = planned.task_id
                        AND task.deleted_at IS NULL
                    RETURNING task.task_id
                )
                UPDATE scheduled_task
                SET
                    starts_at = planned.planned_starts_at,
                    ends_at = planned.planned_ends_at
                FROM planned
                WHERE scheduled_task.task_id = planned.task_id
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
        frequency: RecurrenceFrequency | None = None,
        interval: int | None = None,
    ) -> None:
        if isinstance(data, AddTaskRecurrence):
            frequency = data.frequency
            interval = data.interval
        if frequency is None or interval is None:
            raise ValueError("recurrence frequency and interval are required")

        stmt = text("""
            WITH candidate_occurrence AS (
                SELECT
                    CASE :frequency
                        WHEN 'daily' THEN CAST(:starts_at AS timestamp)
                            + occurrence_index.n * :interval * INTERVAL '1 day'
                        WHEN 'weekly' THEN CAST(:starts_at AS timestamp)
                            + occurrence_index.n * :interval * INTERVAL '1 week'
                        WHEN 'monthly' THEN CAST(:starts_at AS timestamp)
                            + make_interval(months => (occurrence_index.n * :interval)::int)
                    END AS starts_at,
                    CASE :frequency
                        WHEN 'daily' THEN CAST(:ends_at AS timestamp)
                            + occurrence_index.n * :interval * INTERVAL '1 day'
                        WHEN 'weekly' THEN CAST(:ends_at AS timestamp)
                            + occurrence_index.n * :interval * INTERVAL '1 week'
                        WHEN 'monthly' THEN CAST(:ends_at AS timestamp)
                            + make_interval(months => (occurrence_index.n * :interval)::int)
                    END AS ends_at
                FROM generate_series(
                    0,
                    COALESCE(CAST(:occurrences_limit AS integer) - 1, 1000)
                ) AS occurrence_index(n)
            )
            SELECT EXISTS (
                SELECT 1
                FROM candidate_occurrence
                JOIN scheduled_task
                    ON scheduled_task.starts_at < candidate_occurrence.ends_at
                    AND scheduled_task.ends_at > candidate_occurrence.starts_at
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
                    AND (
                        CAST(:repeat_until AS timestamp) IS NULL
                        OR candidate_occurrence.starts_at <= CAST(:repeat_until AS timestamp)
                    )
            ) AS has_overlap
        """)
        result = await self.session.execute(
            stmt,
            {
                "user_id": user_id,
                "task_id": task_id,
                "recurrence_id": recurrence_id,
                "frequency": frequency.value,
                "interval": interval,
                "starts_at": data.schedule.starts_at,
                "ends_at": data.schedule.ends_at,
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
                    rule.starts_at,
                    rule.ends_at,
                    rule.repeat_until,
                    rule.occurrences_limit
                FROM jsonb_to_recordset(CAST(:rules AS jsonb)) AS rule(
                    frequency text,
                    interval integer,
                    starts_at timestamp,
                    ends_at timestamp,
                    repeat_until timestamp,
                    occurrences_limit integer
                )
            ),
            candidate_occurrence AS MATERIALIZED (
                SELECT
                    rule_input.rule_index,
                    CASE rule_input.frequency
                        WHEN 'daily' THEN rule_input.starts_at
                            + occurrence_index.n * rule_input.interval * INTERVAL '1 day'
                        WHEN 'weekly' THEN rule_input.starts_at
                            + occurrence_index.n * rule_input.interval * INTERVAL '1 week'
                        WHEN 'monthly' THEN rule_input.starts_at
                            + make_interval(months => (
                                occurrence_index.n * rule_input.interval
                            )::int)
                    END AS starts_at,
                    CASE rule_input.frequency
                        WHEN 'daily' THEN rule_input.ends_at
                            + occurrence_index.n * rule_input.interval * INTERVAL '1 day'
                        WHEN 'weekly' THEN rule_input.ends_at
                            + occurrence_index.n * rule_input.interval * INTERVAL '1 week'
                        WHEN 'monthly' THEN rule_input.ends_at
                            + make_interval(months => (
                                occurrence_index.n * rule_input.interval
                            )::int)
                    END AS ends_at,
                    rule_input.repeat_until
                FROM rule_input
                CROSS JOIN LATERAL generate_series(
                    0,
                    COALESCE(rule_input.occurrences_limit - 1, 1000)
                ) AS occurrence_index(n)
            ),
            bounded_candidate AS MATERIALIZED (
                SELECT rule_index, starts_at, ends_at
                FROM candidate_occurrence
                WHERE repeat_until IS NULL OR starts_at <= repeat_until
            ),
            existing_overlap AS (
                SELECT 1
                FROM bounded_candidate
                JOIN scheduled_task
                    ON scheduled_task.starts_at < bounded_candidate.ends_at
                    AND scheduled_task.ends_at > bounded_candidate.starts_at
                JOIN task ON task.task_id = scheduled_task.task_id
                WHERE
                    task.creator_id = :user_id
                    AND task.deleted_at IS NULL
                    AND task.status != 'cancelled'
                LIMIT 1
            ),
            internal_overlap AS (
                SELECT 1
                FROM bounded_candidate AS left_candidate
                JOIN bounded_candidate AS right_candidate
                    ON right_candidate.rule_index > left_candidate.rule_index
                    AND right_candidate.starts_at < left_candidate.ends_at
                    AND right_candidate.ends_at > left_candidate.starts_at
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

    async def _replace_recurrence_rule(
        self,
        recurrence_id: UUID,
        data: UpdateTaskRecurrence,
        frequency: RecurrenceFrequency,
    ) -> None:
        deleted_weekdays = (
            delete(TaskRecurrenceWeekdayModel)
            .where(TaskRecurrenceWeekdayModel.series_id == recurrence_id)
            .returning(TaskRecurrenceWeekdayModel.series_id)
            .cte("deleted_recurrence_weekdays")
        )
        deleted_month_rule = (
            delete(TaskRecurrenceMonthRuleModel)
            .where(TaskRecurrenceMonthRuleModel.series_id == recurrence_id)
            .returning(TaskRecurrenceMonthRuleModel.series_id)
            .cte("deleted_recurrence_month_rule")
        )

        if frequency == RecurrenceFrequency.WEEKLY:
            stmt = (
                insert(TaskRecurrenceWeekdayModel)
                .values(
                    series_id=recurrence_id,
                    weekday=data.schedule.starts_at.isoweekday(),
                )
                .add_cte(deleted_weekdays)
                .add_cte(deleted_month_rule)
            )
        elif frequency == RecurrenceFrequency.MONTHLY:
            stmt = (
                insert(TaskRecurrenceMonthRuleModel)
                .values(
                    series_id=recurrence_id,
                    month_day=data.schedule.starts_at.day,
                    business_day_policy=RecurrenceBusinessDayPolicy.NONE,
                )
                .add_cte(deleted_weekdays)
                .add_cte(deleted_month_rule)
            )
        else:
            stmt = select(literal(1)).add_cte(deleted_weekdays).add_cte(deleted_month_rule)

        await self.session.execute(stmt)

    async def _set_recurrence_tasks_status_from(
        self,
        *,
        user_id: UUID,
        recurrence_id: UUID,
        from_datetime: datetime,
        task_status: TaskStatus,
    ) -> None:
        task_ids = self._task_ids_for_recurrence_from(recurrence_id, from_datetime)
        updated_tasks = (
            update(TaskModel)
            .values(status=task_status)
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id.in_(task_ids),
                self._task_is_not_deleted(),
            )
            .returning(TaskModel.task_id)
            .cte("updated_recurrence_tasks")
        )
        await self.session.execute(
            update(TaskRecurrenceInstanceModel)
            .values(is_customized=True)
            .where(
                TaskRecurrenceInstanceModel.series_id == recurrence_id,
                TaskRecurrenceInstanceModel.planned_starts_at >= from_datetime,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .add_cte(updated_tasks)
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
            raise app_exc.TaskNotFound

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

    @classmethod
    def _select_recurrence_template_rows(cls, template_page):
        return (
            select(
                TaskRecurrenceTemplateModel.template_id,
                TaskRecurrenceTemplateModel.title,
                TaskRecurrenceTemplateModel.description,
                TaskRecurrenceTemplateModel.priority,
                TaskRecurrenceTemplateModel.created_at,
                *cls._recurrence_returning_columns(),
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
            .order_by(
                TaskRecurrenceTemplateModel.created_at.desc(),
                TaskRecurrenceTemplateModel.template_id.desc(),
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
            sql_cast(
                literal(data.schedule.starts_at.date()), TaskRecurrenceSeriesModel.anchor_date.type
            ),
            sql_cast(
                literal(data.schedule.starts_at.time()), TaskRecurrenceSeriesModel.default_time.type
            ),
            sql_cast(
                literal(data.schedule.ends_at - data.schedule.starts_at),
                TaskRecurrenceSeriesModel.default_duration.type,
            ),
            sql_cast(
                literal(RecurrenceCalculationMode.SCHEDULED_DATE.value),
                TaskRecurrenceSeriesModel.calculation_mode.type,
            ),
            sql_cast(
                literal(RecurrenceSkipPolicy.ALLOW_OVERDUE.value),
                TaskRecurrenceSeriesModel.skip_policy.type,
            ),
            sql_cast(literal(end_mode.value), TaskRecurrenceSeriesModel.end_mode.type),
            sql_cast(
                literal(data.repeat_until.date() if data.repeat_until else None),
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
                    "calculation_mode",
                    "skip_policy",
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
    def _insert_recurrence_weekday_from_series(inserted_series):
        return (
            pg_insert(TaskRecurrenceWeekdayModel)
            .from_select(
                ("series_id", "weekday"),
                select(
                    inserted_series.c.series_id,
                    sql_cast(func.extract("isodow", inserted_series.c.anchor_date), Integer),
                ).where(inserted_series.c.frequency == RecurrenceFrequency.WEEKLY),
            )
            .on_conflict_do_nothing(index_elements=["series_id", "weekday"])
            .returning(TaskRecurrenceWeekdayModel.series_id)
            .cte("inserted_weekday")
        )

    @staticmethod
    def _insert_recurrence_month_rule_from_series(inserted_series):
        return (
            pg_insert(TaskRecurrenceMonthRuleModel)
            .from_select(
                ("series_id", "month_day", "business_day_policy"),
                select(
                    inserted_series.c.series_id,
                    sql_cast(func.extract("day", inserted_series.c.anchor_date), Integer),
                    sql_cast(
                        literal(RecurrenceBusinessDayPolicy.NONE.value),
                        TaskRecurrenceMonthRuleModel.business_day_policy.type,
                    ),
                ).where(inserted_series.c.frequency == RecurrenceFrequency.MONTHLY),
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
            raise app_exc.TaskNotFound
