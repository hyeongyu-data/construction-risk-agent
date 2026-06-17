"""
Quantity Change Calculator Tool
- 추가 물량 발생 시 자재비 계산
- 계약단가 기준 / 현재단가 기준 / 차액 모두 계산
- 시황성 자재 여부에 따른 주의 메시지 포함
"""

import json
from typing import Optional
from langchain_core.tools import tool


@tool
def calculate_quantity_change_cost(
    material_name: str,
    quantity: float,
    unit: str,
    current_unit_price: float,
    contract_unit_price: Optional[float] = None,
    is_market_sensitive: bool = False,
    contract_type: str = "고정단가",
    vat_included: bool = False,
) -> str:
    """
    추가 물량 발생에 따른 자재비를 계산합니다.

    Args:
        material_name: 자재명 (예: "H파일")
        quantity: 추가 물량 수치 (예: 500)
        unit: 단위 (예: "ton", "m²", "EA")
        current_unit_price: 현재 단가 (원/단위, 조달청 기준)
        contract_unit_price: 계약 단가 (원/단위). None이면 현재단가만으로 계산
        is_market_sensitive: 시황성 자재 여부 (단가 변동 가능성)
        contract_type: 계약 유형 ("고정단가" 또는 "시가연동")
        vat_included: 부가세 포함 여부 (False면 별도 계산)

    Returns:
        계약단가/현재단가 기준 추가비용, 차액, 시황성 주의사항 포함 JSON
    """
    try:
        # --- 현재단가 기준 계산 ---
        cost_by_current = quantity * current_unit_price
        vat_by_current = cost_by_current * 0.1 if not vat_included else 0
        total_by_current = cost_by_current + vat_by_current

        result = {
            "status": "success",
            "자재명": material_name,
            "추가물량": quantity,
            "단위": unit,
            "현재단가_원": current_unit_price,
            "현재단가_기준": {
                "추가자재비_원": round(cost_by_current),
                "부가세_원": round(vat_by_current),
                "합계_원": round(total_by_current),
                "합계_만원": round(total_by_current / 10000, 1),
            },
        }

        # --- 계약단가 기준 계산 (계약단가가 있을 때) ---
        if contract_unit_price is not None and contract_unit_price > 0:
            cost_by_contract = quantity * contract_unit_price
            vat_by_contract = cost_by_contract * 0.1 if not vat_included else 0
            total_by_contract = cost_by_contract + vat_by_contract

            price_diff = current_unit_price - contract_unit_price
            cost_diff = total_by_current - total_by_contract
            diff_ratio = (price_diff / contract_unit_price) * 100

            result["계약단가_원"] = contract_unit_price
            result["계약단가_기준"] = {
                "추가자재비_원": round(cost_by_contract),
                "부가세_원": round(vat_by_contract),
                "합계_원": round(total_by_contract),
                "합계_만원": round(total_by_contract / 10000, 1),
            }
            result["단가차액분석"] = {
                "단가차이_원": round(price_diff),
                "비용차이_원": round(cost_diff),
                "비용차이_만원": round(cost_diff / 10000, 1),
                "단가변동률_pct": round(diff_ratio, 2),
                "현재단가가_더_높음": price_diff > 0,
            }

        # --- 시황성 / 계약유형 주의사항 ---
        notes = []
        if is_market_sensitive:
            notes.append(
                "⚠️ 이 자재는 시황성 자재입니다. "
                "공시 이후 실제 구매 시점에 단가가 달라질 수 있습니다."
            )
        if contract_type == "시가연동":
            notes.append(
                "📋 계약 유형이 '시가연동'입니다. "
                "현재단가 기준으로 청구 가능한지 계약 조건을 확인하세요."
            )
        if contract_unit_price is None:
            notes.append(
                "ℹ️ 계약단가가 입력되지 않았습니다. "
                "Project Context DB에서 계약단가를 확인 후 재계산하세요."
            )
        if not vat_included:
            notes.append("ℹ️ 부가세(10%)는 별도로 계산되었습니다.")

        result["주의사항"] = notes
        result["계약유형"] = contract_type

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"계산 중 오류 발생: {str(e)}"},
            ensure_ascii=False,
        )


@tool
def calculate_total_material_cost(items: list[dict]) -> str:
    """
    여러 자재의 추가비용을 합산합니다.

    Args:
        items: 자재별 비용 딕셔너리 리스트.
               각 항목: {"자재명": str, "추가비용_원": float, "단가기준": str}

    Returns:
        항목별 + 총합 비용 JSON
    """
    try:
        if not items:
            return json.dumps(
                {"status": "error", "message": "items가 비어있습니다."},
                ensure_ascii=False,
            )

        total = 0
        breakdown = []
        for item in items:
            cost = float(item.get("추가비용_원", 0))
            total += cost
            breakdown.append(
                {
                    "자재명": item.get("자재명", "알 수 없음"),
                    "추가비용_원": round(cost),
                    "추가비용_만원": round(cost / 10000, 1),
                    "단가기준": item.get("단가기준", "미확인"),
                }
            )

        return json.dumps(
            {
                "status": "success",
                "항목별_비용": breakdown,
                "총_추가자재비_원": round(total),
                "총_추가자재비_만원": round(total / 10000, 1),
                "총_추가자재비_억원": round(total / 100_000_000, 3),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"합산 오류: {str(e)}"}, ensure_ascii=False
        )
