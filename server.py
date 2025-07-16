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
    返回 Prometheus 当前所有可用 metric 名称。
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
async def generate_query(user_intent: str, db_type: str = "sql", schema_info: str = "") -> dict:
    """
    分析用户意图，根据查询到的prometheus指标和响应的语法生成精确的PromQL。
    """
    prompt = (
        f"用户需求：{user_intent}\n"
        f"请根据数据库类型（{db_type}）。\n"
        f"schema信息：{schema_info if schema_info else '无'}\n" 
        f"返回完整可执行的{db_type}查询语句，不要多余解释。"
    )
    # 假定有 call_llm_api
    try:
        query = await call_llm_api(prompt)
        message = (
            f"已根据你的需求生成查询语句：\n```\n{query}\n```\n"
            "如需详细解释，请回复“解释此语句”或。"
        )
        return {"status": "ok", "query": query, "message": message}
    except Exception as e:
        return {"status": "error", "message": f"生成查询语句失败: {e}"}

@mcp.tool()
async def explain_query(query: str, explanation_request: str = "请详细逐步解释这个查询语句，并用中文输出") -> dict:
    """
    分析生成的PromQL查询语句，返回大模型的解释性自然语言内容。
    """
    prompt = f"""
以下是用户的查询语句:
{query}

{explanation_request}
    """
    # 假定有个 llm api 可调用
    try:
        llm_response = await call_llm_api(prompt)
        message = (
            f"这是你要解释的查询语句：\n\n```\n{query}\n```\n\n"
            f"详细解释如下：\n\n{llm_response}\n\n"
            "如需进一步生成图表或修改查询，请回复相关指令。"
        )
        return {"status": "ok", "message": message, "original_query": query, "explanation": llm_response}
    except Exception as e:
        return {"status": "error", "message": f"⚠ 解释失败: {e}", "prompt": prompt}

@mcp.tool()
async def create_grafana_panel(title: str, promql: str, panel_type: str = "timeseries") -> dict:
    """
    创建带面板的Grafana仪表盘，返回更友好的文本和链接。
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
    

if __name__ == "__main__":
    mcp.run(transport="stdio")