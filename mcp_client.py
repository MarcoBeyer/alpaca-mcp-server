from fastmcp import Client
import asyncio


async def main():
    # The client will automatically handle GitHub OAuth
    async with Client("http://localhost:8000/mcp/", auth="oauth") as client:
        # First-time connection will open GitHub login in your browser
        print("✓ Authenticated with GitHub!")

        # Test the protected tool
        result = await client.call_tool("get_user_info")
        print(f"GitHub user: {result['github_user']}")


if __name__ == "__main__":
    asyncio.run(main())
