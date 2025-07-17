from fastapi import FastAPI

app = FastAPI(title="AI Log Analysis Agent", version="1.0")

@app.get("/")
async def root():
    return {"status": "Log Analysis Agent is running"}
