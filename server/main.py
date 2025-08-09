import mimetypes
import os
import shutil
import tempfile
from typing import Iterator, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from imageio_ffmpeg import get_ffmpeg_exe

app = FastAPI(title="yt-dlp API (single file)")

# CORS (adjust origins if you want to lock it down)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/info")
def info(url: str = Query(..., description="Video URL")):
    try:
        with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            data = ydl.extract_info(url, download=False)
            return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def _iter_file(path: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

def _cleanup(paths: List[str]):
    for p in paths:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

def _pick_downloaded_file(directory: str, prefer_exts: List[str]) -> str | None:
    candidates = []
    for root, _, files in os.walk(directory):
        for name in files:
            # skip temp/side files
            if name.endswith((".part", ".ytdl", ".json", ".xml", ".vtt", ".srt", ".description", ".info.json", ".jpg", ".jpeg", ".png", ".webp")):
                continue
            path = os.path.join(root, name)
            size = os.path.getsize(path)
            candidates.append((size, path))
    if not candidates:
        return None
    # prefer specific extensions first
    by_ext = {os.path.splitext(p)[1].lstrip(".").lower(): p for _, p in sorted(candidates, reverse=True)}
    for ext in prefer_exts:
        if ext in by_ext:
            return by_ext[ext]
    # fallback to largest file
    candidates.sort(reverse=True)
    return candidates[0][1]

@app.get("/download")
def download(
    url: str = Query(..., description="Video URL (single item, not playlist)"),
    kind: str = Query("video", pattern="^(video|audio)$", description="video or audio"),
    audio_format: str = Query("mp3", description="Target audio format if kind=audio (mp3/opus/aac/etc)"),
    video_format: str = Query("mp4", description="Target container if kind=video (mp4 preferred)"),
):
    """
    Downloads ONE file and streams it:
    - kind=audio → bestaudio → convert to audio_format with ffmpeg
    - kind=video → bestvideo+audio merged → try to output as video_format (mp4)
    """
    tmp_dir = tempfile.mkdtemp(prefix="ytdlp-")
    outtmpl = os.path.join(tmp_dir, "%(title).200B [%(id)s].%(ext)s")
    ffmpeg_dir = os.path.dirname(get_ffmpeg_exe())

    if kind == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "noplaylist": True,
            "restrictfilenames": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 10,
            "ffmpeg_location": ffmpeg_dir,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": "192",
                }
            ],
            "prefer_ffmpeg": True,
        }
        prefer_exts = [audio_format, "mp3", "m4a", "opus", "aac"]
    else:
        ydl_opts = {
            "format": "bv*+ba/b",
            "outtmpl": outtmpl,
            "noplaylist": True,
            "restrictfilenames": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 10,
            "ffmpeg_location": ffmpeg_dir,
            "merge_output_format": video_format,  # try mp4
            "prefer_ffmpeg": True,
        }
        prefer_exts = [video_format, "mp4", "mkv", "webm"]

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))

    # pick the final file to stream
    file_path = _pick_downloaded_file(tmp_dir, prefer_exts)
    if not file_path:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Could not find the downloaded media file")

    filename = os.path.basename(file_path)
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        # reasonable defaults
        content_type = "audio/mpeg" if filename.lower().endswith(".mp3") else "video/mp4"

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    bg = BackgroundTask(_cleanup, [tmp_dir, file_path])
    return StreamingResponse(_iter_file(file_path), media_type=content_type, headers=headers, background=bg)
