import logging
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server

from mcp_server.db import init_db
from mcp_server import tools
from mcp_server.watcher import KubeWatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize DB
init_db()

# Create server
server = Server("kubemedic")

@server.list_tools()
async def handle_list_tools() -> list:
    return [
        {
            "name": "get_workload_state",
            "description": "Get deployment state",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "deployment": {"type": "string"}
                }
            }
        },
        {
            "name": "get_pods",
            "description": "Get pod list",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "deployment": {"type": "string"}
                }
            }
        },
        {
            "name": "get_events",
            "description": "Get K8s events",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "deployment": {"type": "string"},
                    "limit": {"type": "integer"}
                }
            }
        },
        {
            "name": "get_recent_changes",
            "description": "Get revision history",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "deployment": {"type": "string"}
                }
            }
        },
        {
            "name": "get_app_health",
            "description": "Get service proxy health check",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "service": {"type": "string"}
                }
            }
        },
        {
            "name": "get_full_snapshot",
            "description": "Get comprehensive state of workload, pods, events, revisions, health",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "deployment": {"type": "string"},
                    "service": {"type": "string"}
                }
            }
        },
        {
            "name": "list_tickets",
            "description": "List tickets from DB",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"}
                }
            }
        },
        {
            "name": "get_ticket",
            "description": "Get single ticket",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"}
                },
                "required": ["ticket_id"]
            }
        },
        {
            "name": "create_ticket",
            "description": "Create a new ticket",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string"},
                    "namespace": {"type": "string"},
                    "deployment": {"type": "string"},
                    "service": {"type": "string"},
                    "signals": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["title", "severity", "namespace", "deployment", "service", "signals"]
            }
        },
        {
            "name": "update_ticket_status",
            "description": "Update ticket status",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "status": {"type": "string"},
                    "detail": {"type": "string"}
                },
                "required": ["ticket_id", "status"]
            }
        }
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list:
    try:
        if name == "get_workload_state":
            result = tools.get_workload_state(**arguments)
        elif name == "get_pods":
            result = tools.get_pods(**arguments)
        elif name == "get_events":
            result = tools.get_events(**arguments)
        elif name == "get_recent_changes":
            result = tools.get_recent_changes(**arguments)
        elif name == "get_app_health":
            result = tools.get_app_health(**arguments)
        elif name == "get_full_snapshot":
            result = tools.get_full_snapshot(**arguments)
        elif name == "list_tickets":
            result = tools.list_tickets(**arguments)
        elif name == "get_ticket":
            result = tools.get_ticket(**arguments)
        elif name == "create_ticket":
            result = tools.create_ticket(**arguments)
        elif name == "update_ticket_status":
            result = tools.update_ticket_status(**arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [{"type": "text", "text": str(result)}]
    except Exception as e:
        logger.error(f"Error calling tool {name}: {e}")
        return [{"type": "text", "text": f"Error: {e}"}]

from mcp.server.models import InitializationOptions

async def run():
    watcher = KubeWatcher()
    watcher.start()
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, 
            write_stream, 
            InitializationOptions(
                server_name="kubemedic",
                server_version="0.1.0",
                capabilities=server.get_capabilities()
            )
        )
        
    watcher.stop()

if __name__ == "__main__":
    asyncio.run(run())

