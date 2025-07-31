import ytdl from 'ytdl-core';

export default async function handler(req, res) {
  const { q } = req.query;

  // Validate the query parameter
  if (!q || typeof q !== "string" || !ytdl.validateURL(q)) {
    console.error("Invalid or missing 'q' parameter:", q);
    return res.status(400).json({ error: 'Query parameter "q" must be a valid YouTube URL.' });
  }

  try {
    console.log(`Fetching info for URL: ${q}`);

    // Use getInfo for more complete data
    const info = await ytdl.getInfo(q, {
      requestOptions: {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
      }
    });

    // Defensive: check if info and videoDetails exist
    if (!info || !info.videoDetails) {
      return res.status(500).json({ error: 'Malformed info object from ytdl-core.' });
    }

    res.status(200).json({
      title: info.videoDetails.title,
      uploader: info.videoDetails.author?.name || null,
      webpage_url: info.videoDetails.video_url,
      lengthSeconds: info.videoDetails.lengthSeconds,
      isLive: info.videoDetails.isLiveContent,
      thumbnails: info.videoDetails.thumbnails,
      formats: info.formats, // for downstream use if needed
    });
  } catch (error) {
    console.error('Error fetching info:', error.message, error.stack);
    if (res.headersSent) return;
    if (error.message.includes('blocked') || error.message.includes('403')) {
      return res.status(403).json({ error: 'Access blocked by YouTube. Try a different URL or add cookies.', details: error.message });
    }
    if (error.message.includes('private') || error.message.includes('age-restricted')) {
      return res.status(403).json({ error: 'This video is private or age-restricted.', details: error.message });
    }
    return res.status(500).json({ error: 'Failed to fetch video info', details: error.message });
  }
}