#!/usr/bin/env python3
"""
DEPRECATED: Alpaca MCP Server with OAuth 2.1 Launcher

This file is deprecated as of the new MCP-auth integration.
OAuth authentication is now handled directly by the FastMCP server
using the built-in MCP OAuth 2.1 framework with GitHubProvider.

For the new OAuth implementation, simply run:
python alpaca_mcp_server.py --transport http

OAuth will be automatically enabled if the environment variables are configured.

This file is kept for backward compatibility but should not be used.
"""

import os
import sys
import subprocess
import signal
import time
import argparse
from dotenv import load_dotenv

def load_config():
    """Load configuration from environment."""
    load_dotenv()
    
    return {
        'oauth_enabled': os.getenv("OAUTH_ENABLED", "false").lower() == "true",
        'github_client_id': os.getenv("GITHUB_CLIENT_ID"),
        'github_client_secret': os.getenv("GITHUB_CLIENT_SECRET"),
        'allowed_email': os.getenv("OAUTH_ALLOWED_EMAIL", "mbeyer2@gmail.com"),
        'secret_key': os.getenv("OAUTH_SECRET_KEY"),
        'alpaca_api_key': os.getenv("ALPACA_API_KEY"),
        'alpaca_secret_key': os.getenv("ALPACA_SECRET_KEY"),
    }

def check_oauth_config(config):
    """Check if OAuth configuration is valid."""
    if not config['oauth_enabled']:
        return True, "OAuth disabled"
    
    missing = []
    if not config['github_client_id']:
        missing.append("GITHUB_CLIENT_ID")
    if not config['github_client_secret']:
        missing.append("GITHUB_CLIENT_SECRET")
    if not config['secret_key']:
        missing.append("OAUTH_SECRET_KEY")
    
    if missing:
        return False, f"Missing OAuth configuration: {', '.join(missing)}"
    
    return True, "OAuth configuration valid"

def check_alpaca_config(config):
    """Check if Alpaca configuration is valid."""
    if not config['alpaca_api_key'] or not config['alpaca_secret_key']:
        return False, "Missing Alpaca API credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY)"
    
    return True, "Alpaca configuration valid"

class ServerManager:
    """Manages MCP server and OAuth proxy processes."""
    
    def __init__(self):
        self.mcp_process = None
        self.proxy_process = None
        self.running = False
    
    def start_mcp_server(self, transport="stdio", host="127.0.0.1", port=8000):
        """Start the MCP server."""
        cmd = [sys.executable, "alpaca_mcp_server.py"]
        
        if transport != "stdio":
            cmd.extend(["--transport", transport, "--host", host, "--port", str(port)])
        
        print(f"Starting MCP server: {' '.join(cmd)}")
        
        self.mcp_process = subprocess.Popen(cmd)
        
        # Give the server time to start
        if transport != "stdio":
            time.sleep(2)
        
        return self.mcp_process
    
    def start_oauth_proxy(self, host="127.0.0.1", proxy_port=8001, mcp_host="127.0.0.1", mcp_port=8000):
        """Start the OAuth proxy."""
        cmd = [
            sys.executable, "oauth_proxy.py",
            "--host", host,
            "--port", str(proxy_port),
            "--mcp-host", mcp_host,
            "--mcp-port", str(mcp_port)
        ]
        
        print(f"Starting OAuth proxy: {' '.join(cmd)}")
        
        self.proxy_process = subprocess.Popen(cmd)
        return self.proxy_process
    
    def stop(self):
        """Stop all processes."""
        self.running = False
        
        if self.proxy_process:
            print("Stopping OAuth proxy...")
            self.proxy_process.terminate()
            try:
                self.proxy_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proxy_process.kill()
        
        if self.mcp_process:
            print("Stopping MCP server...")
            self.mcp_process.terminate()
            try:
                self.mcp_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mcp_process.kill()
    
    def run(self, transport="stdio", host="127.0.0.1", port=8000, proxy_port=8001, oauth_enabled=False):
        """Run the servers."""
        self.running = True
        
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}, shutting down...")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            if transport == "stdio":
                # For stdio, just run the MCP server directly
                self.start_mcp_server(transport=transport)
                
                if self.mcp_process:
                    self.mcp_process.wait()
            
            elif oauth_enabled:
                # Start MCP server on internal port and OAuth proxy on public port
                self.start_mcp_server(transport="http", host="127.0.0.1", port=port)
                
                # Start OAuth proxy
                self.start_oauth_proxy(
                    host=host,
                    proxy_port=proxy_port,
                    mcp_host="127.0.0.1",
                    mcp_port=port
                )
                
                print(f"\nServers started successfully!")
                print(f"MCP Server (internal): http://127.0.0.1:{port}")
                print(f"OAuth Proxy (public): http://{host}:{proxy_port}")
                print(f"Access the server via: http://{host}:{proxy_port}")
                
                # Wait for both processes
                while self.running and self.mcp_process and self.proxy_process:
                    if self.mcp_process.poll() is not None:
                        print("MCP server stopped")
                        break
                    if self.proxy_process.poll() is not None:
                        print("OAuth proxy stopped")
                        break
                    time.sleep(1)
            
            else:
                # Run MCP server directly without OAuth
                self.start_mcp_server(transport=transport, host=host, port=port)
                print(f"\nMCP Server started at: http://{host}:{port}")
                
                if self.mcp_process:
                    self.mcp_process.wait()
        
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

def main():
    parser = argparse.ArgumentParser(description="Alpaca MCP Server with OAuth 2.1")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport method to use (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to for HTTP/SSE transport (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for MCP server (default: 8000)"
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        default=8001,
        help="Port for OAuth proxy when enabled (default: 8001)"
    )
    parser.add_argument(
        "--force-no-oauth",
        action="store_true",
        help="Disable OAuth even if configured"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Check Alpaca configuration
    alpaca_valid, alpaca_msg = check_alpaca_config(config)
    if not alpaca_valid:
        print(f"Error: {alpaca_msg}")
        print("Please configure your Alpaca API credentials in the .env file")
        sys.exit(1)
    
    # Check OAuth configuration
    oauth_valid, oauth_msg = check_oauth_config(config)
    oauth_enabled = config['oauth_enabled'] and oauth_valid and not args.force_no_oauth
    
    print("=== Alpaca MCP Server with OAuth 2.1 ===")
    print(f"Transport: {args.transport}")
    print(f"Alpaca API: {alpaca_msg}")
    print(f"OAuth: {oauth_msg}")
    
    if config['oauth_enabled'] and not oauth_valid:
        print(f"Warning: {oauth_msg}")
        print("OAuth will be disabled. To enable OAuth, please configure:")
        print("- OAUTH_ENABLED=true")
        print("- GITHUB_CLIENT_ID=your_client_id")
        print("- GITHUB_CLIENT_SECRET=your_client_secret")
        print("- OAUTH_SECRET_KEY=your_secret_key")
        print("- OAUTH_ALLOWED_EMAIL=mbeyer2@gmail.com (or your email)")
    
    if oauth_enabled and args.transport == "stdio":
        print("Note: OAuth is not supported with stdio transport. Use --transport http for OAuth.")
        oauth_enabled = False
    
    if oauth_enabled:
        print(f"Allowed email: {config['allowed_email']}")
    
    print("")
    
    # Start servers
    manager = ServerManager()
    manager.run(
        transport=args.transport,
        host=args.host,
        port=args.port,
        proxy_port=args.proxy_port,
        oauth_enabled=oauth_enabled
    )

if __name__ == "__main__":
    main()