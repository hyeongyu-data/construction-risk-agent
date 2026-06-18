"""
건설 리스크 통합 LangGraph (플래너 기반 동적 라우팅)
START → router (플래너: needs_weather + 관련 agents 결정 + Command 핸드오프)
          → needs_weather=True : weather → (계획된 비용 에이전트만 병렬) ┐
          → needs_weather=False: (계획된 비용 에이전트만 병렬)            ├→ synthesize → END
                                                                          ┘
- router_node가 classify_question의 계획(needs_weather, target_agents)에 따라
  Send로 관련 에이전트만 직접 라우팅한다 (A/B 고정 분기 제거, conditional_edges 불필요).
- weather_node도 Command로 직접 라우팅한다: 분석 실패 시 synthesize로 직행,
  성공 시 state['target_agents'](기본 equipment/labor_cost)로만 핸드오프.
  → graph.py에는 weather의 정적 outgoing edge가 없다.
- 비용 에이전트(equipment/material/labor_cost)는 실행되면 synthesize로 모인다.
  계획에서 빠진 에이전트는 애초에 호출되지 않는다.
"""
from langgraph.graph import StateGraph, START, END

from state import RiskState
from nodes.router_node import router_node
from nodes.equipment_node import equipment_node
from nodes.weather_node import weather_node
from nodes.material_node import material_node
from nodes.labor_cost_node import labor_cost_node
from nodes.synthesize_node import synthesize_node


def build_graph():
    wf = StateGraph(RiskState)

    wf.add_node('router', router_node)
    wf.add_node('equipment', equipment_node)
    wf.add_node('material', material_node)
    wf.add_node('labor_cost', labor_cost_node)
    wf.add_node('weather', weather_node)
    wf.add_node('synthesize', synthesize_node)

    wf.add_edge(START, 'router')
    # router_node가 Command로 직접 라우팅 — conditional_edges 불필요

    wf.add_edge('equipment', 'synthesize')
    wf.add_edge('material', 'synthesize')
    wf.add_edge('labor_cost', 'synthesize')
    # weather_node는 Command(goto=...)로 직접 라우팅하므로 정적 edge 불필요
    wf.add_edge('synthesize', END)

    return wf.compile()


graph = build_graph()
