import sqlite3
import os
import logging
from langchain_core.tools import tool

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'db', 'equipment_cost.db'))


@tool
def get_equipment_by_work_type(work_type: str) -> str:
    """
    공종명으로 해당 공종에 투입되는 장비 목록과 임대단가를 조회한다.
    장비명을 모를 때 공종명만으로 장비 대기 비용을 산정하려면 이 도구를 가장 먼저 호출한다.

    work_type: 공종명. 예: '철골 세우기', '콘크리트 타설', '방수공사'
    - 부분 일치 검색 가능. 예: '철골'만 입력해도 '철골 세우기' 결과 반환.
    - 필요구분: 주요(필수 투입) / 조건부(상황에 따라) / 보조(보조 역할)
    - is_standard=1 인 항목이 해당 장비의 표준 규격이다.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT priority, equipment_type, spec, daily_rental_rate, standby_rate, is_standard, year
            FROM equipment_rental
            WHERE work_type LIKE ? OR work_type LIKE '%공통%'
            ORDER BY
                CASE priority WHEN '주요' THEN 1 WHEN '조건부' THEN 2 ELSE 3 END,
                equipment_type,
                is_standard DESC,
                daily_rental_rate
            ''',
            (f'%{work_type}%',),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return (
            f"'{work_type}' 공종을 DB에서 찾을 수 없습니다.\n"
            f"지원 공종: 철골 세우기, 콘크리트 타설, 방수공사\n"
            f"장비명을 직접 입력하려면 get_equipment_rental_rate를 사용하세요."
        )

    year = rows[0][6]
    lines = [f"[{work_type}] 공종 투입 장비 목록 ({year} 기준):"]
    for r in rows:
        priority, eq_type, spec, rate, standby, is_std, _ = r
        std_mark = ' ★표준' if is_std else ''
        lines.append(
            f"  [{priority}] {eq_type} / {spec}{std_mark} — 1일: {rate:,}원, 대기요율: {standby*100:.0f}%"
        )

    logging.info(f'get_equipment_by_work_type: {work_type} → {len(rows)}건')
    return '\n'.join(lines)


@tool
def get_equipment_rental_rate(equipment_type: str) -> str:
    """
    장비 종류로 1일 임대단가와 대기요율을 조회한다.
    장비명을 이미 알고 있을 때 사용한다. 모를 경우 get_equipment_by_work_type을 먼저 호출한다.

    equipment_type: DB의 장비명 기준.
    예: 크레인(타이어), 크레인(무한궤도), 트럭탑재형크레인, 타워크레인,
        콘크리트 펌프차, 콘크리트 믹서트럭, 고소작업차, 지게차, 발전기
    - 부분 일치 검색 가능.
    - ★표준 표시 항목이 규격 미명시 시 기본 선택값이다.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT equipment_type, spec, daily_rental_rate, standby_rate, is_standard, year
            FROM equipment_rental
            WHERE equipment_type LIKE ?
            ORDER BY is_standard DESC, daily_rental_rate
            ''',
            (f'%{equipment_type}%',),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return f'DB에 없는 장비입니다: {equipment_type}'

    lines = []
    for r in rows:
        std_mark = ' ★표준' if r[4] else ''
        lines.append(
            f'[{r[0]} / {r[1]}{std_mark}] 1일 임대단가: {r[2]:,}원, 대기요율: {r[3]*100:.0f}% ({r[5]} 기준)'
        )
    logging.info(f'get_equipment_rental_rate: {equipment_type} → {len(rows)}건')
    return '\n'.join(lines)


@tool
def get_equipment_cost_range(equipment_type: str, delay_days: float) -> str:
    """
    규격이 명시되지 않은 경우 사용한다.
    표준 규격(★) 기준 비용과 최소·최대 규격 비용을 한 번에 계산해 반환한다.

    equipment_type: 장비명. 예: '크레인(타이어)', '콘크리트 펌프차', '타워크레인'
    delay_days: 장비 대기 일수

    반환: 표준 규격 대기 비용 + 최소/최대 규격 비용 범위
    - 표준 규격이 없으면 중간값을 표준으로 사용한다.
    - 계산 결과에서 표준 규격 비용을 대표값으로 사용하고, 범위를 참고값으로 제시한다.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT equipment_type, spec, daily_rental_rate, standby_rate, is_standard
            FROM equipment_rental
            WHERE equipment_type LIKE ?
            ORDER BY daily_rental_rate
            ''',
            (f'%{equipment_type}%',),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return f'DB에 없는 장비입니다: {equipment_type}'

    standby_rate = rows[0][3]

    def calc(rate):
        return int(rate * standby_rate * delay_days)

    # 표준 규격 선택: is_standard=1 우선, 없으면 중간값
    std_row = next((r for r in rows if r[4] == 1), None)
    if std_row is None:
        std_row = rows[len(rows) // 2]
        std_note = '(중간값 자동 선택)'
    else:
        std_note = '(DB 표준 규격)'

    min_row = rows[0]
    max_row = rows[-1]

    eq_name = std_row[0]
    lines = [
        f'[{eq_name}] 규격별 대기 비용 ({delay_days}일, 대기요율 {standby_rate*100:.0f}%)',
        f'',
        f'  ★ 표준 규격 {std_note}',
        f'    {std_row[1]} — {std_row[2]:,}원/일 × {standby_rate} × {delay_days}일 = {calc(std_row[2]):,}원',
        f'',
        f'  ▼ 최소 규격',
        f'    {min_row[1]} — {min_row[2]:,}원/일 × {standby_rate} × {delay_days}일 = {calc(min_row[2]):,}원',
        f'',
        f'  ▲ 최대 규격',
        f'    {max_row[1]} — {max_row[2]:,}원/일 × {standby_rate} × {delay_days}일 = {calc(max_row[2]):,}원',
        f'',
        f'  → 비용 범위: {calc(min_row[2]):,}원 ~ {calc(max_row[2]):,}원',
        f'  → 대표값(표준 규격): {calc(std_row[2]):,}원',
    ]

    logging.info(f'get_equipment_cost_range: {equipment_type} {delay_days}일 → 표준 {calc(std_row[2]):,}원')
    return '\n'.join(lines)


@tool
def calculate_standby_cost(daily_rental_rate: int, standby_rate: float, delay_days: float) -> str:
    """
    장비 1대의 대기 추가 비용을 계산한다.
    규격이 확정된 경우(사용자 명시 또는 표준 규격 선택 후) 사용한다.
    규격이 미명시인 경우에는 get_equipment_cost_range를 사용한다.

    daily_rental_rate : 1일 임대단가 (원)
    standby_rate      : 대기요율 (0.0~1.0). 일반적으로 0.5
    delay_days        : 장비 대기 일수
    """
    standby_day_rate = int(daily_rental_rate * standby_rate)
    total = int(standby_day_rate * delay_days)
    logging.info(f'calculate_standby_cost: {daily_rental_rate:,}원 × {standby_rate} × {delay_days}일 = {total:,}원')
    return (
        f'  1일 임대단가: {daily_rental_rate:,}원\n'
        f'  대기요율: {standby_rate*100:.0f}%\n'
        f'  1일 대기단가: {standby_day_rate:,}원\n'
        f'  지연일수: {delay_days}일\n'
        f'  대기 추가 비용: {standby_day_rate:,}원 × {delay_days}일 = {total:,}원'
    )


@tool
def calculate_total_standby_cost(costs: str) -> str:
    """
    여러 장비의 대기 비용을 합산한다.
    costs: 장비별 대기 비용을 쉼표로 구분한 문자열 (원 단위 정수)
    예: "765000,495000,320000" → 합계 1,580,000원
    """
    try:
        cost_list = [int(c.strip()) for c in costs.split(',') if c.strip()]
    except ValueError:
        return '비용 파싱 오류: 쉼표로 구분된 정수 문자열을 입력하세요. 예: "765000,495000"'

    total = sum(cost_list)
    lines = [f'  장비 {i+1}: {c:,}원' for i, c in enumerate(cost_list)]
    logging.info(f'calculate_total_standby_cost: {cost_list} → 합계 {total:,}원')
    return '장비별 대기 비용:\n' + '\n'.join(lines) + f'\n합계: {total:,}원'
