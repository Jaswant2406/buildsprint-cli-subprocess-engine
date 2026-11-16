"""Verify temp files cleanup over 20 consecutive runs."""
import asyncio
import glob
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.models import Plan
from app.runner import run_tool_async
from app.runstore import RunRecord


async def run_one(idx: int):
    plan = Plan(
        task_type="crawl",
        tool="site_crawler",
        tool_reason="test",
        url="https://example.com",
        max_pages=1,
        max_depth=1,
        wants_summary=False,
        wants_json=True,
    )
    rec = RunRecord(run_id=f"temp-test-{idx}", plan_dict=plan.model_dump(), argv=[])
    events = []
    async for evt in run_tool_async(rec, plan):
        events.append(evt)
    return len(events)

async def main():
    tmp_dir = tempfile.gettempdir()
    pattern = os.path.join(tmp_dir, "tmp*.json")
    before_files = set(glob.glob(pattern))
    print(f"Temp dir: {tmp_dir}")
    print(f"Existing tmp*.json files before test: {len(before_files)}")

    print("Executing 20 runs...")
    for i in range(20):
        await run_one(i)
        if (i + 1) % 5 == 0:
            print(f"  Completed {i + 1}/20 runs")

    after_files = set(glob.glob(pattern))
    leaked = after_files - before_files
    print(f"New tmp*.json files after 20 runs: {len(leaked)}")
    if leaked:
        print(f"FAIL: Leaked temp files: {leaked}")
        sys.exit(1)
    else:
        print("PASS: Exactly 0 accumulated temp files after 20 runs. All cleaned up.")

if __name__ == "__main__":
    asyncio.run(main())
