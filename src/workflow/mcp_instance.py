"""Global MCP server instance management."""

from src.business_logic import FinanceMCP, get_initial_data

# Global MCP instance
_mcp_server = None


def get_mcp_server() -> FinanceMCP:
    """Get the global MCP server instance.
    
    Returns:
        The MCP server instance
    """
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = FinanceMCP(get_initial_data())
    return _mcp_server


def reset_mcp_server():
    """Reset the MCP server with fresh data."""
    global _mcp_server
    _mcp_server = FinanceMCP(get_initial_data())
