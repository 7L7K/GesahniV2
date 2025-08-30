import asyncio
from contextlib import asynccontextmanager

import httpx


@asynccontextmanager
async def client():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as c:
        yield c


async def main():
    ok = True
    async with client() as c:
        ok_codes = {200, 201, 202, 204, 401, 403, 404}
        for path in ["/healthz", "/v1/health", "/metrics"]:
            try:
                r = await c.get(path)
                print(path, r.status_code)
                if r.status_code not in ok_codes:
                    ok = False
            except Exception as e:
                print(path, "ERR", e)
                ok = False
        # Optional: query music state (should 200 even without provider auth)
        try:
            r = await c.get("/v1/state")
            print("/v1/state", r.status_code)
            if r.status_code not in ok_codes:
                ok = False
        except Exception as e:
            print("/v1/state", "ERR", e)
            ok = False
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
