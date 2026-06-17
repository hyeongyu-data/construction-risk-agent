"""라우터 노드 — 분류 후 Command로 다음 에이전트에 직접 핸드오프"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, '..')))

from langchain_core.messages import HumanMessage
from langgraph.types import Command, Send
from router import classify_question
from logger import get_logger

log = get_logger(__name__)


def router_node(state: dict) -> Command:
    log.debug('router_node 진입')
    query = next(
        (m.content for m in reversed(state['messages']) if isinstance(m, HumanMessage)),
        '',
    )
    result = classify_question(query)
    print(f'\n[라우터] {result["type"]} ({result["type_name"]}) — {result["reason"]}')

    if result['type'] == 'A':
        goto = 'weather'
        goto_names = 'weather'
    else:
        goto = [
            Send('equipment', state),
            Send('material', state),
            Send('labor_cost', state),
        ]
        goto_names = 'equipment, material, labor_cost'

    log.info(f"router_node 분기: {result['type']} → {goto_names}")
    return Command(update={'question_type': result['type']}, goto=goto)
