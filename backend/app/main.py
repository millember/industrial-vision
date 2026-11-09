import os

from fastapi import FastAPI

app = FastAPI(
    title=os.getenv("APP_NAME", "Industrial Vision API"),
    root_path=os.getenv("ROOT_PATH", ""),
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
