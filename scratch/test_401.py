import asyncio
from httpx import AsyncClient, ASGITransport
from parikrama.main import create_app

async def main():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/agents/itinerary",
            json={"query": "Plan a 5-day trip from Delhi to Manali"}
        )
        print(resp.status_code)
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(main())
