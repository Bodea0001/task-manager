"""add recurrence date generator

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-15 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the canonical set-based recurrence date generator."""
    op.create_index(
        "ix_scheduled_task_time_range",
        "scheduled_task",
        [sa.text("tsrange(starts_at, ends_at, '[)')")],
        unique=False,
        postgresql_using="gist",
    )
    op.execute("""
        UPDATE task_recurrence_instance AS instance
        SET
            planned_starts_at = COALESCE(
                instance.planned_starts_at,
                instance.planned_date::timestamp + series.default_time
            ),
            planned_ends_at = COALESCE(
                instance.planned_ends_at,
                instance.planned_date::timestamp
                    + series.default_time
                    + COALESCE(series.default_duration, INTERVAL '0 seconds')
            )
        FROM task_recurrence_series AS series
        WHERE
            series.series_id = instance.series_id
            AND (
                instance.planned_starts_at IS NULL
                OR instance.planned_ends_at IS NULL
            )
    """)
    op.drop_constraint(
        op.f("ck_task_recurrence_instance_valid_planned_interval"),
        "task_recurrence_instance",
        type_="check",
    )
    op.alter_column(
        "task_recurrence_instance",
        "planned_starts_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        nullable=False,
        comment="Исходные плановые дата и время",
    )
    op.alter_column(
        "task_recurrence_instance",
        "planned_ends_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        nullable=False,
        comment="Плановый дедлайн экземпляра",
    )
    op.create_check_constraint(
        op.f("ck_task_recurrence_instance_valid_planned_interval"),
        "task_recurrence_instance",
        "planned_ends_at >= planned_starts_at",
    )
    op.execute("""
        CREATE FUNCTION generate_task_recurrence_dates(
            p_frequency text,
            p_step integer,
            p_anchor_date date,
            p_weekdays smallint[],
            p_month_day integer,
            p_week_of_month integer,
            p_month_weekday integer,
            p_business_day_policy text,
            p_starts_on date,
            p_ends_on date,
            p_repeat_until date,
            p_max_occurrences integer
        )
        RETURNS TABLE(sequence_no integer, planned_date date)
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $function$
            WITH bounds AS (
                SELECT
                    p_starts_on AS starts_on,
                    least(p_ends_on, coalesce(p_repeat_until, p_ends_on)) AS ends_on,
                    date_trunc('week', p_anchor_date)::date AS anchor_week,
                    date_trunc('month', p_anchor_date)::date AS anchor_month
            ),
            normalized_weekdays AS (
                SELECT DISTINCT selected.weekday
                FROM unnest(
                    CASE
                        WHEN coalesce(cardinality(p_weekdays), 0) = 0
                            THEN ARRAY[extract(isodow FROM p_anchor_date)::smallint]
                        ELSE p_weekdays
                    END
                ) AS selected(weekday)
            ),
            ranked_weekdays AS (
                SELECT
                    weekday,
                    row_number() OVER (ORDER BY weekday)::integer AS weekday_rank,
                    count(*) OVER ()::integer AS weekday_count,
                    count(*) FILTER (
                        WHERE weekday <= extract(isodow FROM p_anchor_date)::integer
                    ) OVER ()::integer AS weekdays_through_anchor
                FROM normalized_weekdays
            ),
            daily_candidates AS (
                SELECT
                    (period.period_no + 1)::integer AS sequence_no,
                    (
                        p_anchor_date + (period.period_no * p_step)::integer
                    )::date AS planned_date
                FROM bounds
                CROSS JOIN LATERAL generate_series(
                    greatest(
                        0,
                        ceil(
                            ((bounds.starts_on - p_anchor_date)::numeric) / p_step
                        )::integer
                    ),
                    floor(
                        ((bounds.ends_on - p_anchor_date)::numeric) / p_step
                    )::integer
                ) AS period(period_no)
                WHERE
                    p_frequency = 'daily'
                    AND bounds.ends_on >= bounds.starts_on
                    AND (
                        p_max_occurrences IS NULL
                        OR period.period_no + 1 <= p_max_occurrences
                    )
            ),
            weekly_periods AS (
                SELECT period.period_no::integer
                FROM bounds
                CROSS JOIN LATERAL generate_series(
                    greatest(
                        0,
                        (
                            (greatest(bounds.starts_on, p_anchor_date) - bounds.anchor_week)
                            / (7 * p_step)
                        ) - 1
                    ),
                    (bounds.ends_on - bounds.anchor_week) / (7 * p_step)
                ) AS period(period_no)
                WHERE
                    p_frequency = 'weekly'
                    AND bounds.ends_on >= bounds.starts_on
            ),
            weekly_candidates AS (
                SELECT
                    (
                        weekly_periods.period_no * ranked_weekdays.weekday_count
                        + ranked_weekdays.weekday_rank
                        - ranked_weekdays.weekdays_through_anchor
                        + 1
                    )::integer AS sequence_no,
                    (
                        bounds.anchor_week
                        + (
                            weekly_periods.period_no * p_step * 7
                            + ranked_weekdays.weekday - 1
                        )::integer
                    )::date AS planned_date
                FROM bounds
                CROSS JOIN weekly_periods
                CROSS JOIN ranked_weekdays
            ),
            actual_weekly AS (
                SELECT 1 AS sequence_no, p_anchor_date AS planned_date
                WHERE p_frequency = 'weekly'
                UNION ALL
                SELECT sequence_no, planned_date
                FROM weekly_candidates
                WHERE planned_date > p_anchor_date
            ),
            bounded_weekly_candidates AS (
                SELECT actual_weekly.sequence_no, actual_weekly.planned_date
                FROM actual_weekly
                CROSS JOIN bounds
                WHERE
                    actual_weekly.planned_date BETWEEN bounds.starts_on AND bounds.ends_on
                    AND (
                        p_max_occurrences IS NULL
                        OR actual_weekly.sequence_no <= p_max_occurrences
                    )
            ),
            monthly_periods AS (
                SELECT
                    (
                        bounds.anchor_month
                        + make_interval(months => (period.period_no * p_step)::integer)
                    )::date AS month_start
                FROM bounds
                CROSS JOIN LATERAL generate_series(
                    0,
                    greatest(
                        -1,
                        (
                            (
                                extract(year FROM (bounds.ends_on + 2))::integer
                                - extract(year FROM bounds.anchor_month)::integer
                            ) * 12
                            + extract(month FROM (bounds.ends_on + 2))::integer
                            - extract(month FROM bounds.anchor_month)::integer
                        ) / p_step
                    )
                ) AS period(period_no)
                WHERE
                    p_frequency = 'monthly'
                    AND bounds.ends_on >= bounds.starts_on
            ),
            monthly_nominal AS (
                SELECT
                    monthly_periods.month_start,
                    CASE
                        WHEN p_month_day IS NOT NULL THEN (
                            monthly_periods.month_start + (p_month_day - 1)
                        )::date
                        WHEN p_week_of_month = -1 THEN (
                            monthly_periods.month_start
                            + INTERVAL '1 month'
                            - INTERVAL '1 day'
                            - (
                                (
                                    extract(
                                        isodow FROM (
                                            monthly_periods.month_start
                                            + INTERVAL '1 month'
                                            - INTERVAL '1 day'
                                        )
                                    )::integer
                                    - p_month_weekday
                                    + 7
                                ) % 7
                            ) * INTERVAL '1 day'
                        )::date
                        ELSE (
                            monthly_periods.month_start
                            + (
                                (
                                    p_month_weekday
                                    - extract(
                                        isodow FROM monthly_periods.month_start
                                    )::integer
                                    + 7
                                ) % 7
                                + (p_week_of_month - 1) * 7
                            )::integer
                        )::date
                    END AS nominal_date
                FROM monthly_periods
            ),
            valid_monthly_nominal AS (
                SELECT nominal_date
                FROM monthly_nominal
                WHERE date_trunc('month', nominal_date) = month_start
            ),
            adjusted_monthly AS (
                SELECT
                    nominal_date,
                    CASE p_business_day_policy
                        WHEN 'next_business_day' THEN
                            CASE extract(isodow FROM nominal_date)::integer
                                WHEN 6 THEN nominal_date + 2
                                WHEN 7 THEN nominal_date + 1
                                ELSE nominal_date
                            END
                        WHEN 'previous_business_day' THEN
                            CASE extract(isodow FROM nominal_date)::integer
                                WHEN 6 THEN nominal_date - 1
                                WHEN 7 THEN nominal_date - 2
                                ELSE nominal_date
                            END
                        ELSE nominal_date
                    END::date AS planned_date
                FROM valid_monthly_nominal
            ),
            unique_monthly AS (
                SELECT p_anchor_date AS planned_date
                WHERE p_frequency = 'monthly'
                UNION
                SELECT planned_date
                FROM adjusted_monthly
                WHERE nominal_date >= p_anchor_date AND planned_date >= p_anchor_date
            ),
            numbered_monthly AS (
                SELECT
                    row_number() OVER (ORDER BY planned_date)::integer AS sequence_no,
                    planned_date
                FROM unique_monthly
            ),
            bounded_monthly_candidates AS (
                SELECT numbered_monthly.sequence_no, numbered_monthly.planned_date
                FROM numbered_monthly
                CROSS JOIN bounds
                WHERE
                    numbered_monthly.planned_date BETWEEN bounds.starts_on AND bounds.ends_on
                    AND (
                        p_max_occurrences IS NULL
                        OR numbered_monthly.sequence_no <= p_max_occurrences
                    )
            )
            SELECT sequence_no, planned_date FROM daily_candidates
            UNION ALL
            SELECT sequence_no, planned_date FROM bounded_weekly_candidates
            UNION ALL
            SELECT sequence_no, planned_date FROM bounded_monthly_candidates
            ORDER BY sequence_no
        $function$
    """)


def downgrade() -> None:
    """Drop the canonical recurrence date generator."""
    op.execute("""
        DROP FUNCTION generate_task_recurrence_dates(
            text,
            integer,
            date,
            smallint[],
            integer,
            integer,
            integer,
            text,
            date,
            date,
            date,
            integer
        )
    """)
    op.drop_index(
        "ix_scheduled_task_time_range",
        table_name="scheduled_task",
        postgresql_using="gist",
    )
    op.drop_constraint(
        op.f("ck_task_recurrence_instance_valid_planned_interval"),
        "task_recurrence_instance",
        type_="check",
    )
    op.alter_column(
        "task_recurrence_instance",
        "planned_ends_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        nullable=True,
        comment="Плановое окончание, если есть расписание",
    )
    op.alter_column(
        "task_recurrence_instance",
        "planned_starts_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        nullable=True,
        comment="Плановое начало, если есть расписание",
    )
    op.create_check_constraint(
        op.f("ck_task_recurrence_instance_valid_planned_interval"),
        "task_recurrence_instance",
        """
        (
            planned_starts_at IS NULL
            AND planned_ends_at IS NULL
        )
        OR planned_ends_at >= planned_starts_at
        """,
    )
