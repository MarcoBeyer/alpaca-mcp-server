"""
OAuth Proxy Server for Alpaca MCP Server
Acts as an authentication proxy between clients and the MCP server.
"""

import asyncio
import httpx
import os
from typing import Optional
from urllib.parse import urlencode

from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse, JSONResponse, HTMLResponse
from starlette.routing import Route, Mount
import uvicorn

from oauth_auth import OAuthConfig, OAuthManager, create_oauth_routes, is_authenticated


class MCPOAuthProxy:
    """OAuth proxy for MCP server."""
    
    def __init__(self, mcp_host: str = "127.0.0.1", mcp_port: int = 8000, 
                 proxy_port: int = 8001):
        self.mcp_host = mcp_host
        self.mcp_port = mcp_port
        self.proxy_port = proxy_port
        self.mcp_base_url = f"http://{mcp_host}:{mcp_port}"
        
        self.oauth_config = OAuthConfig()
        self.oauth_manager = OAuthManager(self.oauth_config) if self.oauth_config.is_valid() else None
        
        self.app = self._create_app()
    
    def _create_app(self) -> Starlette:
        """Create the Starlette application with OAuth routes and proxy."""
        
        async def proxy_handler(request: Request) -> Response:
            """Proxy requests to the MCP server after authentication."""
            
            # Check authentication if OAuth is enabled
            if self.oauth_config.enabled and not is_authenticated(request, self.oauth_manager):
                return RedirectResponse(url='/auth/login', status_code=302)
            
            # Proxy the request to the MCP server
            async with httpx.AsyncClient() as client:
                url = f"{self.mcp_base_url}{request.url.path}"
                if request.url.query:
                    url += f"?{request.url.query}"
                
                try:
                    # Forward the request
                    response = await client.request(
                        method=request.method,
                        url=url,
                        headers=dict(request.headers),
                        content=await request.body(),
                        timeout=30.0
                    )
                    
                    # Return the response
                    return Response(
                        content=response.content,
                        status_code=response.status_code,
                        headers=dict(response.headers)
                    )
                except httpx.RequestError as e:
                    return JSONResponse(
                        {"error": f"Failed to connect to MCP server: {str(e)}"},
                        status_code=502
                    )
        
        async def home_handler(request: Request) -> Response:
            """Home page with server info."""
            if self.oauth_config.enabled and not is_authenticated(request, self.oauth_manager):
                return RedirectResponse(url='/auth/login', status_code=302)
            
            return HTMLResponse(f"""
                <html><body>
                    <h1>Alpaca MCP Server OAuth Proxy</h1>
                    <p>OAuth authentication is <strong>{'enabled' if self.oauth_config.enabled else 'disabled'}</strong></p>
                    {f'<p>Allowed email: <strong>{self.oauth_config.allowed_email}</strong></p>' if self.oauth_config.enabled else ''}
                    <p>MCP Server: <a href="{self.mcp_base_url}" target="_blank">{self.mcp_base_url}</a></p>
                    {f'<p>User: {request.session.get("user_info", {}).get("email", "Unknown")}</p>' if self.oauth_config.enabled else ''}
                    {f'<a href="/auth/logout">Logout</a>' if self.oauth_config.enabled and is_authenticated(request, self.oauth_manager) else ''}
                </body></html>
            """)
        
        routes = [
            Route('/', home_handler),
        ]
        
        # Add OAuth routes if enabled
        if self.oauth_config.enabled and self.oauth_manager:
            oauth_routes = create_oauth_routes(self.oauth_manager)
            routes.extend(oauth_routes)
        
        # Catch-all route for proxying to MCP server
        routes.append(Route('/{path:path}', proxy_handler, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']))
        
        app = Starlette(routes=routes)
        
        # Add session middleware if OAuth is enabled
        if self.oauth_config.enabled:
            app.add_middleware(SessionMiddleware, secret_key=self.oauth_config.secret_key)
        
        return app
    
    def run(self, host: str = "127.0.0.1"):
        """Run the OAuth proxy server."""
        print(f"Starting OAuth Proxy on {host}:{self.proxy_port}")
        print(f"Proxying to MCP Server at {self.mcp_base_url}")
        if self.oauth_config.enabled:
            print(f"OAuth enabled for email: {self.oauth_config.allowed_email}")
        else:
            print("OAuth disabled - all requests will be proxied without authentication")
        
        uvicorn.run(self.app, host=host, port=self.proxy_port, log_level="info")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="OAuth Proxy for Alpaca MCP Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind proxy server")
    parser.add_argument("--port", type=int, default=8001, help="Port for proxy server")
    parser.add_argument("--mcp-host", default="127.0.0.1", help="MCP server host")
    parser.add_argument("--mcp-port", type=int, default=8000, help="MCP server port")
    
    args = parser.parse_args()
    
    proxy = MCPOAuthProxy(
        mcp_host=args.mcp_host,
        mcp_port=args.mcp_port,
        proxy_port=args.port
    )
    
    proxy.run(host=args.host)