import contentDisposition from "content-disposition";
import execa from "execa";
import pathToFfmpeg from "ffmpeg-static";
import absoluteUrl from "next-absolute-url";
import fetch from "node-fetch";
import queryString from "query-string";

const handler = async (req, res) => {
  const {
    query: { url, f = "bestvideo+bestaudio/best" }, // Default format if not provided
  } = req;

  if (!url || typeof url !== "string") {
    return res.status(400).send("URL parameter is required and must be a string");
  }

  try {
    const { origin } = absoluteUrl(req);
    const data = await fetch(
      `${origin}/api/info?${queryString.stringify({ f, q: url })}`
    );

    if (data.status !== 200) {
      const errorText = await data.text();
      return res.status(400).send(`Info fetch failed: ${errorText}`);
    }

    const info = await data.json();

    if (!info || typeof info !== "object") {
      return res.status(400).send("Invalid response from info endpoint");
    }

    if (info.entries) {
      return res.status(400).send("This endpoint does not support playlists");
    }

    const audioOnly = info.acodec !== "none" && info.vcodec === "none";
    if (info.acodec === "none" && info.vcodec !== "none") {
      return res.status(400).send("Only video, no audio is not supported");
    }

    const ffmpegArgs = ["-i", info.url || (info.requested_formats && info.requested_formats[0]?.url)];
    if (!ffmpegArgs[1]) {
      return res.status(400).send("No valid input URL found in info response");
    }

    if (audioOnly) {
      res.setHeader("Content-Type", "audio/mpeg3");
      ffmpegArgs.push("-acodec", "libmp3lame", "-f", "mp3");
    } else {
      res.setHeader("Content-Type", "video/mp4");
      if (info.requested_formats && info.requested_formats.length > 1) {
        ffmpegArgs.push("-i", info.requested_formats[1].url);
      }
      ffmpegArgs.push(
        "-c:v",
        "libx264",
        "-acodec",
        "aac",
        "-movflags",
        "frag_keyframe+empty_moov",
        "-f",
        "mp4"
      );
    }

    res.setHeader(
      "Content-Disposition",
      contentDisposition(`${info.title || "download"}.${audioOnly ? "mp3" : "mp4"}`)
    );

    ffmpegArgs.push("-");
    const ffSp = execa(pathToFfmpeg, ffmpegArgs, { stdio: ["pipe", "pipe", "pipe"] });
    ffSp.stdout.pipe(res);

    // Handle process errors
    ffSp.on("error", (err) => {
      res.status(500).send(`FFmpeg error: ${err.message}`);
    });

    await ffSp;
  } catch (error) {
    console.error("Download error:", error); // Log error for debugging
    return res.status(400).send(`Processing failed: ${error.message || error.stderr || "Unknown error"}`);
  }
};

export default handler;
