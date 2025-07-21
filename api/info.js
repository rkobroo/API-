import ytdl from 'ytdl-core';

export default async function handler(req, res) {
  const { q } = req.query; // Use 'q' for query parameter

  // Validate query parameter
  if (!q || typeof q !== "string" || q.trim() === "") {
    console.error("Invalid or missing 'q' parameter:", q);
    return res.status(400).json({ error: 'Query parameter "q" is required and must be a valid URL' });
  }

  try {
    console.log(`Fetching info for URL: ${q}`);

    // Configure ytdl-core with headers to mimic a browser request
    const info = await ytdl.getBasicInfo(q, {
      quality: 'lowest',
      requestOptions: {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
          // Add cookies if required (e.g., from a logged-in session)
          // 'Cookie': 'your_cookie_here',
        },
      },
    });

    // Return basic video details
    res.status(200).json({
      title: info.videoDetails.title,
      uploader: info.videoDetails.author.name,
      webpage_url: info.videoDetails.video_url,
    });
  } catch (error) {
    console.error('Error fetching info:', error.message, error.stack);
    if (error.message.includes('blocked') || error.message.includes('403')) {
      return res.status(403).json({ error: 'Access blocked by YouTube. Try with a different URL or add cookies.', details: error.message });
    }
    res.status(500).json({ error: 'Failed to fetch info', details: error.message });
  }
}
