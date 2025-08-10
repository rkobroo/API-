import os
import subprocess
import urllib.parse
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from imageio_ffmpeg import get_ffmpeg_exe

app = FastAPI(title="YouTube Downloader API", description="yt-dlp API")

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Home HTML UI
# -------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Downloader API</title>
        <style>
            body { font-family: Arial; max-width: 700px; margin:auto; padding:20px; }
            input[type=text] { width:100%; padding:10px; margin:10px 0; }
            button { padding:10px 15px; cursor:pointer; }
            pre { background:#f4f4f4; padding:10px; white-space: pre-wrap; }
            a.button { display:inline-block; padding:8px 12px; background:#28a745;
                       color:white; text-decoration:none; border-radius:4px; margin-top:10px; }
            a.audio { background:#007bff; }
        </style>
    </head>
    <body>
        <h1>🎬 YouTube Downloader API</h1>
        <form id="infoForm">
            <label>Video URL:</label>
            <input type="text" id="yturl" placeholder="https://www.youtube.com/watch?v=xxxxx" required>
            <button type="submit">Get Info</button>
        </form>
        <div id="infoOutput"></div>
        <script>
            document.getElementById('infoForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                let url = document.getElementById('yturl').value.trim();
                if(!url) return;
                document.getElementById('infoOutput').innerHTML = '<p>Loading...</p>';
                try {
                    const resp = await fetch('/info?q=' + encodeURIComponent(url));
                    const data = await resp.json();
                    let html = '';
                    if(data.detail){
                        html = '<p style="color:red;">Error: ' + data.detail + '</p>';
                    } else {
                        html += '<h2>Video Info</h2><pre>' + JSON.stringify(data, null, 2) + '</pre>';
                        if(data.webpage_url){
                            html += '<a class="button" target="_blank" href="/download?url=' + encodeURIComponent(url) + '">⬇ Download Video</a>';
                            html += '<a class="button audio" target="_blank" href="/download?url=' + encodeURIComponent(url) + '&f=bestaudio">🎧 Download Audio</a>';
                        }
                    }
                    document.getElementById('infoOutput').innerHTML = html;
                } catch(err){
                    document.getElementById('infoOutput').innerHTML = '<p style="color:red;">Fetch failed: ' + err + '</p>';
                }
            });
        </script>
    </body>
    </html>
    """

# -------------------------
# Health Check
# -------------------------
@app.get("/health")
def health():
    return {"ok": True}

# -------------------------
# Info Endpoint
# -------------------------
@app.get("/info")
def get_video_info(q: str = Query(..., description="Video URL")):
    if not q.strip():
        raise HTTPException(status_code=400, detail='Parameter "q" must be a valid URL.')

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
            "entries": info.get("entries"),
            "http_headers": info.get("http_headers")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch video info: {str(e)}")

# -------------------------
# Download Endpoint (Fixed for Facebook/YouTube/etc.)
# -------------------------
@app.get("/download")
def download_video(
    url: str = Query(..., description="Video URL"),
    f: str = Query("bestvideo+bestaudio/best", description="Format for yt-dlp")
):
    if not url.strip():
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
        raise HTTPException(status_code=400, detail="Only video without audio is not supported")

    input_url = info.get("url") or (info.get("requested_formats")[0]["url"] if info.get("requested_formats") else None)
    if not input_url:
        raise HTTPException(status_code=400, detail="No valid input URL found in info response")

    # Get http headers needed for ffmpeg
    headers = []
    if "http_headers" in info:
        for k, v in info["http_headers"].items():
            headers.extend(["-headers", f"{k}: {v}"])

    ffmpeg_path = get_ffmpeg_exe()
    ffmpeg_args = headers + ["-i", input_url]

    filename = f"{info.get('title', 'download').replace('/', '_')}"
    if audio_only or f == "bestaudio":
        content_type = "audio/mpeg"
        filename += ".mp3"
        ffmpeg_args += ["-acodec", "libmp3lame", "-f", "mp3"]
    else:
        content_type = "video/mp4"
        if info.get("requested_formats") and len(info["requested_formats"]) > 1 and info["requested_formats"][1].get("url"):
            ffmpeg_args += headers + ["-i", info["requested_formats"][1]["url"]]
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

    return StreamingResponse(iterfile(),
                              media_type=content_type,
                              headers={"Content-Disposition": f'attachment; filename="{filename}"'})
