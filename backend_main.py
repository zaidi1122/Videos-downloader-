from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import asyncio
from pathlib import Path

app = FastAPI(title="VidSnap API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

class VideoRequest(BaseModel):
    url: str
    quality: str = "best"  # best, 1080, 720, 480, 360, audio

class InfoRequest(BaseModel):
    url: str

def cleanup_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except:
        pass

@app.get("/")
def root():
    return {"status": "VidSnap API running", "supported": "YouTube, TikTok, Instagram, Facebook, Twitter/X, and 1000+ more"}

@app.post("/info")
async def get_video_info(req: InfoRequest):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            formats = []
            seen = set()
            for f in (info.get("formats") or []):
                height = f.get("height")
                ext = f.get("ext")
                vcodec = f.get("vcodec", "none")
                acodec = f.get("acodec", "none")
                if vcodec != "none" and height:
                    key = (height, ext)
                    if key not in seen:
                        seen.add(key)
                        formats.append({
                            "format_id": f["format_id"],
                            "height": height,
                            "ext": ext,
                            "filesize": f.get("filesize"),
                            "label": f"{height}p ({ext})"
                        })
            formats.sort(key=lambda x: x["height"], reverse=True)
            return {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "platform": info.get("extractor_key"),
                "formats": formats[:8],
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/download")
async def download_video(req: VideoRequest, background_tasks: BackgroundTasks):
    file_id = str(uuid.uuid4())
    output_path = DOWNLOAD_DIR / f"{file_id}.%(ext)s"

    quality_map = {
        "best":  "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080":  "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "720":   "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "480":   "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
        "360":   "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best",
        "audio": "bestaudio[ext=m4a]/bestaudio",
    }

    format_str = quality_map.get(req.quality, quality_map["best"])

    ydl_opts = {
        "format": format_str,
        "outtmpl": str(output_path),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            title = info.get("title", "video")

        # Find downloaded file
        downloaded = list(DOWNLOAD_DIR.glob(f"{file_id}.*"))
        if not downloaded:
            raise HTTPException(status_code=500, detail="Download failed")

        file_path = str(downloaded[0])
        ext = downloaded[0].suffix

        media_type = "audio/mp4" if req.quality == "audio" else "video/mp4"
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:60]
        filename = f"{safe_title}{ext}"

        background_tasks.add_task(cleanup_file, file_path)

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
