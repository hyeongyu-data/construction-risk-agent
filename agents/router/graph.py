"""
건설 리스크 통합 LangGraph
START → router (분류 + Command 핸드오프)
          → A: weather → END
          → B: equipment ┐
                material  ├ 병렬 → END
                labor_cost┘
"""
from langgraph.graph import StateGraph, START, END

from state import RiskState
from nodes.router_node import router_node
from nodes.equipment_node import equipment_node
from nodes.weather_node import weather_node
from nodes.material_node import material_node
from nodes.labor_cost_node import labor_cost_node


def build_graph():
    wf = StateGraph(RiskState)

    wf.add_node('router', router_node)
    wf.add_node('equipment', equipment_node)
    wf.add_node('material', material_node)
    wf.add_node('labor_cost', labor_cost_node)
    wf.add_node('weather', weather_node)

    wf.add_edge(START, 'router')
    # router_node가 Command로 직접 라우팅 — conditional_edges 불필요

    wf.add_edge('equipment', END)
    wf.add_edge('material', END)
    wf.add_edge('labor_cost', END)
    wf.add_edge('weather', END)

    return wf.compile()


graph = build_graph()
