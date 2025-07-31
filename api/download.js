import contentDisposition from "content-disposition";
import execa from "execa";
import pathToFfmpeg from "ffmpeg-static";
import absoluteUrl from "next-absolute-url";
import fetch from "node-fetch";
import queryString from "query-string";

const handler = async (req, res) => {
  const {
    query: { url, f = "bestvideo+bestaudio/best" },
  } = req;

  // Validate URL parameter
  if (!url || typeof url !== "string" || url.trim() === "") {
    console.error("Invalid or missing URL parameter:", url);
    return res.status(400).send("URL parameter is required and cannot be empty");
  }

  let responded = false;
  let ffSp = null;

  // Clean up FFmpeg if client disconnects
  res.on("close", () => {
    if (ffSp && ffSp.kill) ffSp.kill("SIGKILL");
  });

  try {
    const { origin } = absoluteUrl(req);
    const infoUrl = `${origin}/api/info?${queryString.stringify({ f, q: url })}`;
    console.log(`Fetching info from: ${infoUrl}`);
    const data = await fetch(infoUrl);

    if (data.status !== 200) {
      const errorText = await data.text();
      console.error(`Info endpoint failed: ${errorText}`);
      responded = true;
      return res.status(400).send(`Info fetch failed: ${errorText}`);
    }

    const info = await data.json();
    console.log("Info response:", JSON.stringify(info));

    if (!info || typeof info !== "object") {
      responded = true;
      return res.status(400).send("Invalid response from info endpoint");
    }

    if (info.entries) {
      responded = true;
      return res.status(400).send("This endpoint does not support playlists");
    }

    const audioOnly = info.acodec !== "none" && info.vcodec === "none";
    if (info.acodec === "none" && info.vcodec !== "none") {
      responded = true;
      return res.status(400).send("Only video, no audio is not supported");
    }

    const inputUrl = info.url || (Array.isArray(info.requested_formats) && info.requested_formats[0]?.url);
    if (!inputUrl) {
      responded = true;
      return res.status(400).send("No valid input URL found in info response");
    }

    const ffmpegArgs = ["-i", inputUrl];
    if (audioOnly) {
      res.setHeader("Content-Type", "audio/mpeg3");
      ffmpegArgs.push("-acodec", "libmp3lame", "-f", "mp3");
    } else {
      res.setHeader("Content-Type", "video/mp4");
      if (Array.isArray(info.requested_formats) && info.requested_formats.length > 1) {
        ffmpegArgs.push("-i", info.requested_formats[1].url);
      }
      ffmpegArgs.push(
        "-c:v", "libx264",
        "-acodec", "aac",
        "-movflags", "frag_keyframe+empty_moov",
        "-f", "mp4"
      );
    }

    res.setHeader(
      "Content-Disposition",
      contentDisposition(`${info.title || "download"}.${audioOnly ? "mp3" : "mp4"}`)
    );

    ffmpegArgs.push("-");
    console.log("FFmpeg args:", ffmpegArgs);
    ffSp = execa(pathToFfmpeg, ffmpegArgs, { stdio: ["pipe", "pipe", "pipe"] });
    ffSp.stdout.pipe(res);

    ffSp.on("error", (err) => {
      if (!responded) {
        responded = true;
        console.error("FFmpeg execution error:", err.message);
        if (!res.headersSent)
          res.status(500).send(`FFmpeg error: ${err.message}`);
      }
    });

    await ffSp;
  } catch (error) {
    if (!responded) {
      responded = true;
      console.error("Handler error:", error.message, error.stack);
      if (!res.headersSent)
        return res.status(500).send(`Processing failed: ${error.message || "Unknown error"}`);
    }
  }
};

export default handler;