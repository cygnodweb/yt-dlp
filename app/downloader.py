import yt_dlp
import uuid

def download_video(url):
    file_id = str(uuid.uuid4())
    output = f"downloads/{file_id}.mp4"

    ydl_opts = {
        "format": "mp4",
        "outtmpl": output,
        "cookiefile": "app/cookies.txt",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return output
