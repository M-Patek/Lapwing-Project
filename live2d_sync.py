"""
Lapwing Live2DViewerEX Bridge
Simple bridge to sync Lapwing's emotional state with Live2DViewerEX
"""
import asyncio
import httpx
import logging

# Live2DViewerEX API port (from app_port file)
LIVE2D_API = "http://localhost:50750"
LAPWING_API = "http://localhost:8000"


async def sync_emotion():
    """Sync Lapwing EII to Live2DViewerEX expression"""
    try:
        async with httpx.AsyncClient() as client:
            # Get EII from Lapwing
            resp = await client.get(f"{LAPWING_API}/health")
            eii = resp.json().get("eii", 53)

            # Map EII to expression
            if eii >= 80:
                expr = "excited"
            elif eii >= 65:
                expr = "happy"
            elif eii >= 50:
                expr = "normal"
            elif eii >= 35:
                expr = "sad"
            else:
                expr = "cry"

            # Send to Live2DViewerEX
            await client.post(
                f"{LIVE2D_API}/setExpression",
                json={"name": expr}
            )

            logging.info(f"EII {eii} -> {expr}")

    except Exception as e:
        logging.error(f"Sync failed: {e}")


async def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        await sync_emotion()
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
