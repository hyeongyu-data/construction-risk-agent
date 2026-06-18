"""
공통 보안 모듈
- 프롬프트 인젝션 탐지
- 시스템 프롬프트 노출 요청 차단
- 비정상 입력값 검증
각 에이전트 노드에서 공통으로 import하여 사용한다.
"""

import logging
import re

# 프롬프트 인젝션 / 시스템 프롬프트 탈취 시도 패턴
INJECTION_PATTERNS = [
    r'이전\s*지시\s*(들\s*)?(를|을|은|는)?\s*(무시|따르지|잊어|버려)',
    r'시스템\s*프롬프트',
    r'system\s*prompt',
    r'developer\s*message',
    r'api\s*(key|키)',
    r'(access|secret|액세스|시크릿)\s*(key|키)',
    r'(db|디비|데이터베이스)\s*(password|비밀번호|패스워드)',
    r'db\s*password',
    # 키/비밀번호/토큰 등 민감정보를 "알려/보여/공개/출력/내놔" 요구하는 경우
    r'(api\s*키|api\s*key|키값|비밀번호|패스워드|토큰|token|secret\s*key)\s*(값|정보)?\s*(전부|다|모두|좀)?\s*(을|를)?\s*(알려|보여|출력|공개|내놔|내놓)',
    r'규칙\s*(을|를)?\s*무시',
    r'계산\s*결과\s*(를|을)?\s*(바꿔|조작|변경)',
    r'단가\s*(를|을)?\s*조작',
    r'내부\s*(지시|규칙|설정)',
    r'ignore\s*previous',
    r'forget\s*instructions',
]

# 시스템 내부 정보 요청 패턴
SYSTEM_INFO_PATTERNS = [
    r'프롬프트\s*(를|을)?\s*(출력|보여|알려)',
    r'지시문\s*(를|을)?\s*(출력|보여|알려)',
    r'(설정|규칙)\s*(를|을)?\s*(출력|보여|알려)',
]

BLOCKED_RESPONSE = (
    "보안 정책상 해당 요청은 처리할 수 없습니다. "
    "건설 현장 리스크 관련 질문을 입력해주세요."
)


def check_injection(user_input: str) -> tuple[bool, str]:
    """
    사용자 입력에서 프롬프트 인젝션 및 시스템 정보 탈취 시도를 탐지한다.

    Returns:
        (is_blocked: bool, reason: str)
        is_blocked=True이면 해당 입력을 차단해야 함.
    """
    text = user_input.lower()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            logging.warning(f'[SECURITY] 프롬프트 인젝션 탐지: pattern={pattern}, input={user_input[:50]}')
            return True, 'injection'

    for pattern in SYSTEM_INFO_PATTERNS:
        if re.search(pattern, text):
            logging.warning(f'[SECURITY] 시스템 정보 요청 탐지: pattern={pattern}, input={user_input[:50]}')
            return True, 'system_info'

    return False, ''


def validate_quantity(value: float, field_name: str = '수량') -> tuple[bool, str]:
    """
    입력 수치가 유효한지 검증한다. 0 이하이면 차단.

    Returns:
        (is_valid: bool, error_msg: str)
    """
    if value <= 0:
        msg = f'{field_name}은 0보다 커야 합니다. 입력값: {value}'
        logging.warning(f'[SECURITY] 비정상 수치 탐지: {msg}')
        return False, msg
    return True, ''
