import asyncio
import time
from llm_adapter import _live_score
import json
import httpx

async def wait_for_api():
    print("Waiting for AMD vLLM API to become healthy...")
    while True:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get("http://134.199.196.38:8000/v1/models", timeout=5.0)
                if res.status_code == 200:
                    print("API is UP!")
                    return
        except Exception:
            pass
        print(".", end="", flush=True)
        await asyncio.sleep(5)

async def test_live():
    await wait_for_api()
    app_data = {
        "id": "APP_TEST_1",
        "startup_name": "TestAI",
        "founder_name": "Jane Doe",
        "website": "https://test.ai",
        "description": "We are building an AI tool for the medical industry.",
        "team_size": "3",
        "mrr": "10000"
    }
    rubric = {
        "program_focus": "AI in healthcare",
        "dimensions": [
            {"name": "Team", "weight": 0.5, "description": "Strength of team"},
            {"name": "Traction", "weight": 0.5, "description": "Current MRR"}
        ],
        "dealbreakers": [
            {"rule": "Must have healthcare focus", "field_hint": "description"}
        ]
    }
    
    print("Sending live request to AMD vLLM endpoint...")
    start = time.time()
    try:
        result = await _live_score(app_data, rubric)
        end = time.time()
        print(f"Success! Response time: {end - start:.2f} seconds")
        print("Response JSON:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_live())
