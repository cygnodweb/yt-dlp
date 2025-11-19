const express = require('express');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const { v4: uuidv4 } = require('uuid');
const morgan = require('morgan');

const PORT = process.env.PORT || 3000;
const DOWNLOAD_DIR = path.join(__dirname, 'public', 'downloads');
if (!fs.existsSync(DOWNLOAD_DIR)) fs.mkdirSync(DOWNLOAD_DIR, { recursive: true });

const app = express();
app.use(express.json({ limit: '10mb' }));
app.use(morgan('combined'));
app.use('/downloads', express.static(DOWNLOAD_DIR)); // serve files

app.get('/ping', (req, res) => res.json({ status: 'ok', ts: Date.now() }));

/**
 * POST /download
 * body: { url: string, format: 'mp4'|'mkv'|..., opts?: object }
 * response: { downloadUrl: string, fileName: string }
 */
app.post('/download', async (req, res) => {
  const { url, format = 'mp4' } = req.body || {};
  if (!url) return res.status(400).json({ error: 'Missing url' });

  const id = uuidv4();
  const outName = `${id}.%(ext)s`;
  const outPath = path.join(DOWNLOAD_DIR, outName);

  // Build yt-dlp args. Ensure yt-dlp is installed on the host.
  const args = [
    '--no-playlist',
    '--format', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
    '--merge-output-format', format,
    '--output', outPath,
    url
  ];

  // spawn yt-dlp
  execFile('yt-dlp', args, { timeout: 1000 * 60 * 5 }, (err, stdout, stderr) => {
    if (err) {
      console.error('yt-dlp error', err, stderr);
      return res.status(500).json({ error: 'download_failed', detail: stderr || err.message });
    }

    // Resolve the generated file (first match)
    const files = fs.readdirSync(DOWNLOAD_DIR);
    const file = files.find(f => f.startsWith(id + '.'));
    if (!file) return res.status(500).json({ error: 'no_output_file' });

    const downloadUrl = `${req.protocol}://${req.get('host')}/downloads/${encodeURIComponent(file)}`;
    return res.json({ downloadUrl, fileName: file });
  });
});

// lightweight cleanup: optional endpoint to remove files older than X hours
app.post('/cleanup', (req, res) => {
  const maxAgeHours = Number(process.env.MAX_AGE_HOURS || 6);
  const now = Date.now();
  const removed = [];
  fs.readdirSync(DOWNLOAD_DIR).forEach(fn => {
    const fp = path.join(DOWNLOAD_DIR, fn);
    const stat = fs.statSync(fp);
    const ageH = (now - stat.mtimeMs) / (1000 * 3600);
    if (ageH > maxAgeHours) {
      fs.unlinkSync(fp);
      removed.push(fn);
    }
  });
  res.json({ removed });
});

app.listen(PORT, () => {
  console.log(`YT-DLP render server running on port ${PORT}`);
});
