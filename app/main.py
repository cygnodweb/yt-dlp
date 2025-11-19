from fastapi import FastAPI, HTTPException
from downloader import download_video

app = FastAPI()

@app.get("/")
def home():
    return {"message": "YT Downloader Running"}

@app.get("/download")
def download(url: str):
    try:
        file_path = download_video(url)
        return {"status": "success", "file": file_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
