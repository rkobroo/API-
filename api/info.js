import ytdl from 'ytdl-core';

export default async function handler(req, res) {
  const { url } = req.query;
  if (!url) return res.status(400).json({ error: 'URL is required' });

  try {
    const info = await ytdl.getBasicInfo(url, { quality: 'lowest' }); // Fetch basic info only
    res.status(200).json({
      title: info.videoDetails.title,
      uploader: info.videoDetails.author.name,
      webpage_url: info.videoDetails.video_url,
    });
  } catch (error) {
    console.error('Error fetching info:', error);
    res.status(500).json({ error: 'Failed to fetch info', details: error.message });
  }
}
