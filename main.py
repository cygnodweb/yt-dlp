from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import subprocess
import os
import uuid

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok", "message": "YouTube Downloader API Working"}

@app.post("/download")
def download_video(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="Missing url")

    # Unique filename for each request
    video_id = str(uuid.uuid4())
    output_file = f"{video_id}.mp4"

    # yt-dlp command with cookies + retries + undetectable switches
    command = [
        "yt-dlp",
        "--no-warnings",
        "--cookies", "cookies.txt",  # Optional
        "-f", "mp4",
        "--retries", "15",
        "--fragment-retries", "15",
        "--geo-bypass",
        "-o", output_file,
        url
    ]

    try:
        # Run yt-dlp
        result = subprocess.run(command, capture_output=True, text=True)

        # If any error
        if result.returncode != 0:
            print(result.stderr)
            raise HTTPException(status_code=500, detail="Download failed. Check cookies.")

        # File exists?
        if not os.path.exists(output_file):
            raise HTTPException(status_code=500, detail="Video not saved")

        # Return downloadable file
        return FileResponse(
            output_file,
            media_type="video/mp4",
            filename="video.mp4"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
