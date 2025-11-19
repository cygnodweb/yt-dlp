from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import os
import uuid
import json

app = FastAPI()

class DownloadRequest(BaseModel):
    url: str

@app.post("/download")
def download_video(req: DownloadRequest):
    url = req.url
    video_id = str(uuid.uuid4())
    output_path = f"{video_id}.mp4"
    json_path = f"{video_id}.json"

    # yt-dlp command with cookies for bypass
    cmd = [
        "yt-dlp",
        "--cookies", "cookies.txt",
        "--write-info-json",
        "--no-warnings",
        "--no-call-home",
        "-o", video_id,
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr)

    json_file = f"{video_id}.info.json"

    if not os.path.exists(json_file):
        raise HTTPException(status_code=500, detail="Metadata not found.")

    with open(json_file, "r") as f:
        metadata = json.load(f)

    title = metadata.get("title", "No title found")
    description = metadata.get("description", "")

    video_file = f"{video_id}.mp4"

    if not os.path.exists(video_file):
        raise HTTPException(status_code=500, detail="Video download failed.")

    response = {
        "title": title,
        "description": description,
        "video_file": video_file
    }

    return response

@app.get("/file/{filename}")
def get_file(filename: str):
    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(filename, media_type="video/mp4")
