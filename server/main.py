import os
import subprocess
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from imageio_ffmpeg import get_ffmpeg_exe

app = FastAPI(title="YouTube Downloader API", description="yt-dlp API")

# Allow all origins — change to specific domain if you want security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Root Welcome Page
# -------------------------
@app.get("/")
def root():
    return {
        "message": "Welcome to the YouTube Downloader API 🎬",
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "info": "/info?q=<YouTube URL>",
            "download": "/download?url=<YouTube URL>&f=bestvideo+bestaudio/best"
        }
    }

# -------------------------
# Health Check
# -------------------------
@app.get("/health")
def health():
    return {"ok": True}

# -------------------------
# Info Endpoint (replacement for info.js)
# -------------------------
@app.get("/info")
def get_video_info(q: str = Query(..., description="YouTube video URL")):
    if not q or not isinstance(q, str):
        raise HTTPException(status_code=400, detail='Parameter "q" is required and must be a string.')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(q, download=False)

        if not info:
            raise HTTPException(status_code=500, detail="No information retrieved.")

        return {
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "webpage_url": info.get("webpage_url"),
            "lengthSeconds": info.get("duration"),
            "isLive": info.get("is_live"),
            "thumbnails": info.get("thumbnails", []),
            "formats": info.get("formats", []),
            "acodec": info.get("acodec"),
            "vcodec": info.get("vcodec"),
            "requested_formats": info.get("requested_formats"),
            "url": info.get("url"),
            "entries": info.get("entries")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch video info: {str(e)}")

# -------------------------
# Download Endpoint (replacement for download.js)
# -------------------------
@app.get("/download")
def download_video(
    url: str = Query(..., description="Video URL"),
    f: str = Query("bestvideo+bestaudio/best", description="Format for yt-dlp")
):
    if not url or not isinstance(url, str) or url.strip() == "":
        raise HTTPException(status_code=400, detail="URL parameter is required and cannot be empty")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': f,
        'skip_download': True
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"yt-dlp error: {str(e)}")

    if info.get("entries"):
        raise HTTPException(status_code=400, detail="This endpoint does not support playlists")

    audio_only = info.get("acodec") != "none" and info.get("vcodec") == "none"
    if info.get("acodec") == "none" and info.get("vcodec") != "none":
        raise HTTPException(status_code=400, detail="Video without audio is not supported")

    input_url = info.get("url") or (info.get("requested_formats")[0]["url"] if info.get("requested_formats") else None)
    if not input_url:
        raise HTTPException(status_code=400, detail="No valid input URL found")

    ffmpeg_path = get_ffmpeg_exe()
    ffmpeg_args = ["-i", input_url]

    filename = f"{info.get('title', 'download').replace('/', '_')}"
    if audio_only:
        content_type = "audio/mpeg"
        filename += ".mp3"
        ffmpeg_args += ["-acodec", "libmp3lame", "-f", "mp3"]
    else:
        content_type = "video/mp4"
        if info.get("requested_formats") and len(info["requested_formats"]) > 1:
            ffmpeg_args += ["-i", info["requested_formats"][1]["url"]]
        ffmpeg_args += [
            "-c:v", "libx264",
            "-acodec", "aac",
            "-movflags", "frag_keyframe+empty_moov",
            "-f", "mp4"
        ]
        filename += ".mp4"

    ffmpeg_args.append("-")

    def iterfile():
        process = subprocess.Popen(
            [ffmpeg_path, *ffmpeg_args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        try:
            while True:
                chunk = process.stdout.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iterfile(), media_type=content_type, headers=headers)
