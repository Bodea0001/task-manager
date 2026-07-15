from uuid import UUID
from datetime import datetime, timedelta
from dataclasses import asdict

from sqlalchemy import delete, select, text, bindparam
from sqlalchemy.types import TIMESTAMP
from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert

import exceptions as app_exc
from models.tasks import Task as TaskModel, ScheduledTask as ScheduledTaskModel
from domain.value_objects.tasks import FreeTime, Schedule, Task, TaskStatus
from adapters.repositories.task_repository_common import (
    TaskRepositoryCommon,
    translate_repository_errors,
)


class TaskScheduleMixin(TaskRepositoryCommon):
    async def get_free_time(self, user_id: UUID, windows: tuple[Schedule, ...]) -> list[FreeTime]:
        stmt = text("""
            WITH requested_window AS (
                SELECT row_number() OVER () AS window_index, starts_at, ends_at
                FROM unnest(
                    CAST(:window_starts AS timestamp[]),
                    CAST(:window_ends AS timestamp[])
                ) AS requested(starts_at, ends_at)
            ),
            busy AS (
                SELECT
                    requested_window.window_index,
                    greatest(scheduled_task.starts_at, requested_window.starts_at) AS starts_at,
                    least(scheduled_task.ends_at, requested_window.ends_at) AS ends_at
                FROM requested_window
                JOIN scheduled_task
                    ON tsrange(scheduled_task.starts_at, scheduled_task.ends_at, '[)')
                        && tsrange(
                            requested_window.starts_at,
                            requested_window.ends_at,
                            '[)'
                        )
                JOIN task ON task.task_id = scheduled_task.task_id
                WHERE
                    task.creator_id = :user_id
                    AND task.deleted_at IS NULL
                    AND task.status != 'cancelled'
            ),
            ordered_busy AS (
                SELECT
                    window_index,
                    starts_at,
                    ends_at,
                    lead(starts_at) OVER (
                        PARTITION BY window_index
                        ORDER BY starts_at, ends_at
                    ) AS next_starts_at
                FROM busy
            ),
            gaps AS (
                SELECT
                    requested_window.window_index,
                    requested_window.starts_at AS starts_at,
                    min(busy.starts_at) AS ends_at
                FROM requested_window
                JOIN busy ON busy.window_index = requested_window.window_index
                GROUP BY requested_window.window_index, requested_window.starts_at

                UNION ALL

                SELECT window_index, ends_at AS starts_at, next_starts_at AS ends_at
                FROM ordered_busy
                WHERE next_starts_at IS NOT NULL

                UNION ALL

                SELECT
                    requested_window.window_index,
                    max(busy.ends_at) AS starts_at,
                    requested_window.ends_at AS ends_at
                FROM requested_window
                JOIN busy ON busy.window_index = requested_window.window_index
                GROUP BY requested_window.window_index, requested_window.ends_at

                UNION ALL

                SELECT window_index, starts_at, ends_at
                FROM requested_window
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM busy
                    WHERE busy.window_index = requested_window.window_index
                )
            )
            SELECT starts_at, ends_at
            FROM gaps
            WHERE starts_at < ends_at
            ORDER BY starts_at, ends_at
        """).bindparams(
            bindparam("window_starts", type_=ARRAY(TIMESTAMP(timezone=False))),
            bindparam("window_ends", type_=ARRAY(TIMESTAMP(timezone=False))),
        )

        result = await self.session.execute(
            stmt,
            {
                "user_id": user_id,
                "window_starts": [window.starts_at for window in windows],
                "window_ends": [window.ends_at for window in windows],
            },
        )
        return [self._row_to_free_time(row) for row in result.all()]

    async def get_schedule_blocking_tasks(self, user_id: UUID, window: Schedule) -> list[Task]:
        stmt = (
            self._select_task_list_rows_with_tags()
            .join(ScheduledTaskModel, ScheduledTaskModel.task_id == TaskModel.task_id)
            .where(
                TaskModel.creator_id == user_id,
                self._task_is_not_deleted(),
                TaskModel.status != TaskStatus.CANCELLED,
                ScheduledTaskModel.starts_at < window.ends_at,
                ScheduledTaskModel.ends_at > window.starts_at,
            )
            .order_by(TaskModel.due_at, TaskModel.created_at)
        )

        result = await self.session.execute(stmt)
        return self._task_list_rows_to_tasks(result.all())

    async def find_nearest_free_schedule(
        self,
        user_id: UUID,
        duration: timedelta,
        excluded_windows: tuple[Schedule, ...],
        search_from: datetime,
    ) -> Schedule:
        stmt = text("""
            WITH excluded_window AS (
                SELECT starts_at, ends_at
                FROM unnest(
                    CAST(:excluded_starts AS timestamp[]),
                    CAST(:excluded_ends AS timestamp[])
                ) AS excluded(starts_at, ends_at)
            ),
            busy AS (
                SELECT scheduled_task.starts_at, scheduled_task.ends_at
                FROM scheduled_task
                JOIN task ON task.task_id = scheduled_task.task_id
                WHERE
                    task.creator_id = :user_id
                    AND task.deleted_at IS NULL
                    AND task.status != 'cancelled'
                    AND scheduled_task.ends_at > :search_from

                UNION ALL

                SELECT starts_at, ends_at
                FROM excluded_window
                WHERE ends_at > :search_from
            ),
            candidate AS (
                SELECT :search_from AS starts_at

                UNION

                SELECT ends_at AS starts_at
                FROM busy
                WHERE ends_at >= :search_from
            )
            SELECT
                candidate.starts_at,
                candidate.starts_at + (:duration_seconds * INTERVAL '1 second') AS ends_at
            FROM candidate
            WHERE NOT EXISTS (
                SELECT 1
                FROM busy
                WHERE
                    busy.starts_at < candidate.starts_at + (
                        :duration_seconds * INTERVAL '1 second'
                    )
                    AND busy.ends_at > candidate.starts_at
            )
            ORDER BY candidate.starts_at
            LIMIT 1
        """).bindparams(
            bindparam("excluded_starts", type_=ARRAY(TIMESTAMP(timezone=False))),
            bindparam("excluded_ends", type_=ARRAY(TIMESTAMP(timezone=False))),
        )

        result = await self.session.execute(
            stmt,
            {
                "user_id": user_id,
                "duration_seconds": duration.total_seconds(),
                "excluded_starts": [window.starts_at for window in excluded_windows],
                "excluded_ends": [window.ends_at for window in excluded_windows],
                "search_from": search_from,
            },
        )
        return self._row_to_schedule(result.one())

    @translate_repository_errors
    async def add_schedule_to_task(self, user_id: UUID, task_id: UUID, schedule: Schedule):
        await self._upsert_task_schedule(user_id, task_id, schedule)

    async def delete_schedule_from_task(self, user_id: UUID, task_id: UUID):
        stmt = delete(ScheduledTaskModel).where(
            ScheduledTaskModel.task_id == task_id,
            select(1)
            .select_from(TaskModel)
            .where(TaskModel.creator_id == user_id, TaskModel.task_id == ScheduledTaskModel.task_id)
            .where(self._task_is_not_deleted())
            .exists(),
        )

        await self.session.execute(stmt)

    async def _upsert_task_schedule(self, user_id: UUID, task_id: UUID, schedule: Schedule | None):
        if not schedule:
            return

        await self._raise_if_schedule_overlaps(user_id, task_id, schedule)

        values = asdict(schedule)

        stmt = (
            pg_insert(ScheduledTaskModel)
            .values(task_id=task_id, **values)
            .on_conflict_do_update(index_elements=["task_id"], set_=values)
        )

        await self.session.execute(stmt)

    async def _raise_if_schedule_overlaps(self, user_id: UUID, task_id: UUID, schedule: Schedule):
        stmt = select(
            select(1)
            .select_from(ScheduledTaskModel)
            .join(TaskModel, TaskModel.task_id == ScheduledTaskModel.task_id)
            .where(
                TaskModel.creator_id == user_id,
                self._task_is_not_deleted(),
                TaskModel.status != TaskStatus.CANCELLED,
                ScheduledTaskModel.task_id != task_id,
                ScheduledTaskModel.starts_at < schedule.ends_at,
                ScheduledTaskModel.ends_at > schedule.starts_at,
            )
            .exists()
        )

        result = await self.session.execute(stmt)
        if result.scalar_one():
            raise app_exc.TaskScheduleOverlap
