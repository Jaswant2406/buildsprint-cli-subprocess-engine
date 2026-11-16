"""Test 3 simultaneous requests against production HTTP server."""
import asyncio

import httpx


async def fire(idx: int):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(
                "http://127.0.0.1:8000/api/chat",
                json={"prompt": f"Crawl https://example.com for run {idx}"},
            )
            # Read first line
            async for line in res.aiter_lines():
                if line.strip():
                    return f"Req {idx}: HTTP {res.status_code} -> {line[:80]}"
            return f"Req {idx}: HTTP {res.status_code}"
        except Exception as e:
            return f"Req {idx}: ERROR -> {e}"

async def main():
    results = await asyncio.gather(fire(1), fire(2), fire(3), fire(4), fire(5), fire(6))
    for r in results:
        print(r)

if __name__ == "__main__":
    asyncio.run(main())
