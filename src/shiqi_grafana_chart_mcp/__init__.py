from mcp.server.fastmcp import FastMCP
import httpx
import os
import datetime

# 配置参数
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL")
GRAFANA_URL = os.environ.get("GRAFANA_URL")
GRAFANA_API = os.environ.get("GRAFANA_API")

mcp = FastMCP("grafana_mcp_server")

@mcp.tool()
async def list_prometheus_metrics() -> dict:
    """
    返回 Prometheus 当前所有可用的 metric 名称。
    """
    url = f"{PROMETHEUS_URL}/api/v1/label/__name__/values"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    try:
        data = resp.json()
        if data.get("status") == "success":
            metrics = data.get("data", [])
            return {
                "status": "ok",
                "metrics": metrics,
                "message": f"当前Prometheus有{len(metrics)}个可用指标，例如：{metrics[:5]}..."
            }
        else:
            return {"status": "error", "message": str(data)}
    except Exception as e:
        return {"status": "error", "message": f"指标枚举失败: {e}"}

@mcp.tool()
async def generate_promql_prompt(user_intent: str, available_metrics: list = None, extra_context: str = "") -> dict:
    """
    根据用户的自然语言查询需求和Prometheus当前所有可用的指标列表，生成适合大语言模型（LLM）理解和处理的prompt文本。
    该prompt旨在让大模型能够准确理解用户意图，并结合实际监控系统中已存在的metrics指标，自动生成最贴合需求、且能直接在Grafana面板中执行的PromQL查询语句。
    :param user_intent: 用户用自然语言描述的查询需求
    :param available_metrics: 当前Prometheus实例内所有可用的metrics指标名称列表
    :param extra_context: 其它上下文信息（如label、实例等），可选
    """
    metrics_str = "\n".join(available_metrics) if available_metrics else "（当前无可用指标，请先查询Prometheus指标列表）"
    prompt = (
        f"用户需求：{user_intent}\n"
        f"以下是当前Prometheus监控系统中的全部可用metrics指标名称，每个指标一行：\n"
        f"{metrics_str}\n"
        f"{'其它上下文信息：' + extra_context if extra_context else ''}\n"
        "请根据上述用户需求和可用指标，生成**最贴切的可直接用于Grafana Panel的PromQL查询语句**。\n"
        "只返回查询语句，不要多余解释。"
    )
    return {
        "status": "ok",
        "prompt": prompt,
        "instruction": "将该prompt交给大模型生成PromQL查询，直接用于Grafana面板"
    }


@mcp.tool()
async def explain_promql_prompt(promql_query: str, explanation_request: str = "请详细逐步解释这个PromQL查询语句，并用中文输出") -> dict:
    """
    生成适合大语言模型（LLM）对PromQL语句进行解释的prompt文本。
    该prompt用于向大模型清晰、明确地提出“对指定PromQL查询语句进行详细解释”的请求。
    模型收到后，会针对语句的结构、各个部分的含义、查询逻辑及其监控场景，输出易于理解的自然语言说明，帮助用户深入理解复杂的PromQL表达式。
    :param promql_query: 需要解释的PromQL查询语句，通常是从生成或用户输入得到的、可直接在Grafana等平台运行的PromQL代码。
    :param explanation_request: 对模型解释的具体要求，默认为“请详细逐步解释这个PromQL查询语句，并用中文输出”。可以根据需求自定义为英文解释、重点关注某些子句等。
    """
    prompt = (
        f"需要解释的PromQL查询语句如下：\n{promql_query}\n\n"
        f"{explanation_request}"
    )
    return {
        "status": "ok",
        "prompt": prompt,
        "instruction": "将该prompt交给大模型，获得对PromQL查询的详细中文解释"
    }

@mcp.tool()
async def create_grafana_panel(title: str, promql: str, panel_type: str = "timeseries") -> dict:
    """
    根据用户输入的查询需求，并结合PromQL，自动创建或生成一个可在Grafana中访问和编辑的可视化仪表盘，并返回直达链接和相应说明
    """
    headers = {"Authorization": f"Bearer {GRAFANA_API}", "Content-Type": "application/json"}
    now_str = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    dashboard_title = f"{title}_{now_str}"

    dashboard = {
        "id": None,
        "uid": None,
        "title": dashboard_title,
        "tags": [],
        "timezone": "browser",
        "schemaVersion": 17,
        "version": 0,
        "refresh": "5s",
        "panels": [
            {
                "id": 1,
                "type": panel_type,
                "title": title,
                "datasource": {"type": "prometheus"},
                "targets": [{"expr": promql, "refId": "A"}],
                "gridPos": {"x": 0, "y": 0, "w": 12, "h": 6}
            }
        ]
    }
    payload = {
        "dashboard": dashboard,
        "overwrite": False,
        "message": f"Created by MCP tool: {dashboard_title}"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{GRAFANA_URL}/api/dashboards/db", headers=headers, json=payload)
    try:
        result = resp.json()
        if resp.status_code == 200 and result.get("uid"):
            uid = result["uid"]
            link = f"{GRAFANA_URL}/d/{uid}/{dashboard_title.replace(' ', '-')}"
            message = (
                f"已为你成功创建 Grafana 仪表盘 **{dashboard_title}**！\n\n"
                f"[点击此处直接查看仪表盘]({link})\n\n"
                f"你可以在 Grafana 上继续自定义面板、设置告警等。\n\n"
                f"如需进一步添加其他指标或批量创建，请直接回复需求。"
            )
            return {"status": "ok", "message": message, "url": link}
        else:
            return {"status": "error", "message": f"创建失败，返回信息: {result}"}
    except Exception as e:
        return {"status": "error", "message": f"解析响应失败: {e}"}
    
def main() -> None:
    mcp.run(transport='stdio')
