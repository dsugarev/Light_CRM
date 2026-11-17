"""Pydantic request and response schemas."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.sales.schemas import (
    ConversionFigures,
    ForecastReport,
    PipelineReport,
    WinLossFigures,
)

ReportName = Literal["pipeline-by-stage", "forecast", "lead-conversion", "win-loss"]


class TaskFigures(BaseModel):
    open: int
    overdue: int


class Dashboard(BaseModel):
    """FR-REP-01: everything the dashboard shows, for one owner scope and period."""

    from_date: date
    to_date: date
    pipeline: PipelineReport
    forecast: ForecastReport
    lead_conversion: ConversionFigures
    win_loss: WinLossFigures
    my_tasks: TaskFigures = Field(description="The caller's own tasks, whatever the owner filter")
