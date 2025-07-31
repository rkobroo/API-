from starlette.responses import JSONResponse, PlainTextResponse
import youtube_dl
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from youtube_dl.version import __version__ as youtube_dl_version
import youtube_dl.utils

DEFAULT_FORMAT = "bestvideo+bestaudio/best"
DEFAULT_SEARCH = "ytsearch10"

app = FastAPI(docs_url=None, redoc_url=None)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return PlainTextResponse(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

@app.get("/api/info", status_code=status.HTTP_200_OK)
async def get_info(q: str, f: str = DEFAULT_FORMAT):
    if not q or not isinstance(q, str) or q.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'q' is required and must be a non-empty string.",
            headers={"Cache-Control": "no-store, max-age=0"}
        )
    try:
        ydl_opts = {
            "default_search": DEFAULT_SEARCH,
            "format": f.replace(" ", "+"),
            "retries": 3,
            "encoding": "utf8",
            "socket_timeout": 10,
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(q, download=False)
            return JSONResponse(res, headers={"Cache-Control": "s-maxage=2592000, stale-while-revalidate"})
    except youtube_dl.utils.DownloadError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Download error: {str(e)}",
            headers={"Cache-Control": "no-store, max-age=0"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
            headers={"Cache-Control": "no-store, max-age=0"}
        )

@app.get("/api/version", status_code=status.HTTP_200_OK)
async def get_version():
    return PlainTextResponse(youtube_dl_version)