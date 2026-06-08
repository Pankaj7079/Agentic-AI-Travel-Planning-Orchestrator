import asyncio
from httpx import AsyncClient
from parikrama.main import create_app
from fastapi.testclient import TestClient

app = create_app()
client = TestClient(app)

# Let's bypass auth check using a generic mock or just run it and get the 401, but we want the 422
# Wait, TestClient without auth returns 401. But let's look at the body for 401 and 422 if we mock auth.
from parikrama.core.security import get_current_user_id
app.dependency_overrides[get_current_user_id] = lambda: "test-user-id"

resp = client.post(
    "/api/v1/agents/itinerary",
    json={"query": "Plan a 5-day trip from Delhi to Manali"}
)
print(resp.status_code)
print(resp.json())
