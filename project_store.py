"""
프로젝트 샘플 데이터 로더

TODO: 실제 DB 연결로 교체 시 이 파일만 수정하면 됨.
      get_project() 인터페이스는 그대로 유지.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from weather_risk.models import WeatherRiskRequest, WorkType

KST = ZoneInfo("Asia/Seoul")

_DATA_PATH = Path(__file__).resolve().parent / "sample_projects.json"


def _load() -> dict:
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def get_project(project_id: str, query_date: datetime | None = None) -> WeatherRiskRequest:
    """
    project_id로 프로젝트 정보를 조회해 WeatherRiskRequest로 반환.

    query_date: 분석 기준 날짜 (None이면 오늘). KST-aware datetime.
    TODO: 실제 DB 조회로 교체.
    """
    projects = _load()

    if project_id not in projects:
        available = list(projects.keys())
        raise KeyError(f"project_id '{project_id}' not found. available: {available}")

    p = projects[project_id]

    base_date = (query_date or datetime.now(KST)).date()

    start_h, start_m = map(int, p["scheduled_start_time"].split(":"))
    end_h, end_m = map(int, p["scheduled_end_time"].split(":"))

    scheduled_start = datetime(base_date.year, base_date.month, base_date.day,
                               start_h, start_m, tzinfo=KST)
    scheduled_end = datetime(base_date.year, base_date.month, base_date.day,
                             end_h, end_m, tzinfo=KST)

    return WeatherRiskRequest(
        project_id=p["project_id"],
        site_name=p["site_name"],
        latitude=p["latitude"],
        longitude=p["longitude"],
        work_type=WorkType(p["work_type"]),
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        query_type="SHORT_TERM",
    )