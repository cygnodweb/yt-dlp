from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import requests
import os
import tempfile
import logging
import threading
import time
from urllib.parse import urlparse, parse_qs
import yt_dlp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration - Using your API key
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', 'AIzaSyBRoWTktLPtebrpk5l41xnREXtC9Oa2rag')
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# Ensure templates directory exists
os.makedirs('templates', exist_ok=True)

class YouTubeAPIDownloader:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.api_key = YOUTUBE_API_KEY
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.cookies_file = "cookies.txt"
        
        # Check if cookies file exists
        if os.path.exists(self.cookies_file):
            logger.info(f"Cookies file found: {self.cookies_file}")
        else:
            logger.warning(f"Cookies file not found: {self.cookies_file}")
        
    def extract_video_id(self, url):
        """Extract video ID from various YouTube URL formats"""
        try:
            if 'youtube.com/watch' in url:
                parsed_url = urlparse(url)
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
                return video_id
            elif 'youtu.be/' in url:
                return url.split('youtu.be/')[-1].split('?')[0]
            elif 'youtube.com/shorts/' in url:
                return url.split('/shorts/')[-1].split('?')[0]
            elif 'youtube.com/embed/' in url:
                return url.split('/embed/')[-1].split('?')[0]
            return None
        except:
            return None
    
    def get_video_info(self, video_id):
        """Get video information using YouTube API"""
        try:
            url = f"{self.base_url}/videos"
            params = {
                'part': 'snippet,contentDetails,statistics',
                'id': video_id,
                'key': self.api_key
            }
            
            logger.info(f"Fetching video info for: {video_id}")
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if not data.get('items'):
                return {'error': 'Video not found or unavailable'}
            
            item = data['items'][0]
            snippet = item['snippet']
            content_details = item['contentDetails']
            statistics = item.get('statistics', {})
            
            # Parse duration (ISO 8601 format to readable)
            duration = self.parse_duration(content_details['duration'])
            
            return {
                'success': True,
                'title': snippet['title'],
                'description': snippet['description'][:200] + '...' if len(snippet.get('description', '')) > 200 else snippet.get('description', ''),
                'thumbnail': snippet['thumbnails']['high']['url'],
                'channel_title': snippet['channelTitle'],
                'published_at': snippet['publishedAt'][:10],  # Just date
                'duration': duration,
                'view_count': statistics.get('viewCount', '0'),
                'like_count': statistics.get('likeCount', '0'),
                'comment_count': statistics.get('commentCount', '0'),
                'video_id': video_id
            }
            
        except Exception as e:
            logger.error(f"API Error: {e}")
            return {'error': f'Failed to fetch video info: {str(e)}'}
    
    def parse_duration(self, duration):
        """Convert ISO 8601 duration to readable format"""
        # Remove 'PT' prefix
        duration = duration[2:]
        time_parts = []
        
        # Extract hours
        if 'H' in duration:
            hours, duration = duration.split('H')
            time_parts.append(f"{hours}h")
        
        # Extract minutes
        if 'M' in duration:
            minutes, duration = duration.split('M')
            time_parts.append(f"{minutes}m")
        
        # Extract seconds
        if 'S' in duration:
            seconds = duration.split('S')[0]
            time_parts.append(f"{seconds}s")
        
        return ' '.join(time_parts) if time_parts else 'Unknown'
    
    def search_videos(self, query, max_results=10):
        """Search for videos using YouTube API"""
        try:
            url = f"{self.base_url}/search"
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'maxResults': max_results,
                'key': self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            videos = []
            for item in data.get('items', []):
                videos.append({
                    'video_id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description'],
                    'thumbnail': item['snippet']['thumbnails']['high']['url'],
                    'channel_title': item['snippet']['channelTitle'],
                    'published_at': item['snippet']['publishedAt']
                })
            
            return {'success': True, 'videos': videos}
            
        except Exception as e:
            logger.error(f"Search Error: {e}")
            return {'error': f'Search failed: {str(e)}'}
    
    def download_video(self, video_id, format_type='best'):
        """Download video using yt-dlp with cookies and API verification"""
        try:
            # First verify video exists using API
            video_info = self.get_video_info(video_id)
            if 'error' in video_info:
                return video_info
            
            logger.info(f"Downloading video: {video_info['title']}")
            
            # Configure yt-dlp options with cookies
            ydl_opts = {
                'outtmpl': os.path.join(self.temp_dir, f'%(title).100s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                # Enhanced anti-detection settings
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                },
                'sleep_interval': 2,
                'max_sleep_interval': 5,
            }
            
            # Add cookies if available
            if os.path.exists(self.cookies_file):
                ydl_opts['cookiefile'] = self.cookies_file
                logger.info("Using cookies for authentication")
            
            if format_type == 'audio':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
            elif format_type == 'video_720':
                ydl_opts['format'] = 'best[height<=720]'
            elif format_type == 'video_480':
                ydl_opts['format'] = 'best[height<=480]'
            elif format_type == 'video_360':
                ydl_opts['format'] = 'best[height<=360]'
            else:
                ydl_opts['format'] = 'best[height<=720]'
            
            # Download the video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                url = f'https://www.youtube.com/watch?v={video_id}'
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                if format_type == 'audio':
                    filename = filename.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                
                return {
                    'success': True,
                    'filename': filename,
                    'title': info.get('title', 'video'),
                    'video_id': video_id
                }
                
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Download error: {e}")
            # Try alternative approach if cookies fail
            return self.try_alternative_download(video_id, format_type, str(e))
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {'error': f'Unexpected error: {str(e)}'}
    
    def try_alternative_download(self, video_id, format_type, original_error):
        """Try alternative download methods when primary fails"""
        logger.info("Trying alternative download method...")
        
        try:
            # Method 1: Try without cookies (sometimes works for public videos)
            ydl_opts = {
                'outtmpl': os.path.join(self.temp_dir, f'{video_id}.%(ext)s'),
                'quiet': True,
                'format': 'worst[height<=360]',  # Lower quality might work better
            }
            
            if format_type == 'audio':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '128',
                    }],
                })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                url = f'https://www.youtube.com/watch?v={video_id}'
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                if format_type == 'audio':
                    filename = filename.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                
                logger.info("Alternative download method succeeded!")
                return {
                    'success': True,
                    'filename': filename,
                    'title': info.get('title', 'video'),
                    'video_id': video_id
                }
                
        except Exception as e:
            logger.error(f"Alternative download also failed: {e}")
            return {'error': f'Download failed: YouTube is blocking downloads from this server. Original error: {original_error}'}

downloader = YouTubeAPIDownloader()

# Background cleanup
def cleanup_old_files():
    while True:
        time.sleep(3600)  # Clean every hour
        try:
            for filename in os.listdir(downloader.temp_dir):
                filepath = os.path.join(downloader.temp_dir, filename)
                if os.path.isfile(filepath):
                    file_age = time.time() - os.path.getctime(filepath)
                    if file_age > 3600:
                        os.remove(filepath)
                        logger.info(f"Cleaned up: {filename}")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

# Create default HTML template if it doesn't exist
def create_default_template():
    template_path = 'templates/index_api.html'
    if not os.path.exists(template_path):
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube API Downloader</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: white; border-radius: 15px; padding: 30px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #333; margin-bottom: 10px; }
        .input-group { margin-bottom: 20px; }
        .url-input { width: 100%; padding: 15px; border: 2px solid #ddd; border-radius: 8px; font-size: 16px; }
        .format-buttons { display: flex; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
        .format-btn { padding: 10px 20px; border: 2px solid #667eea; background: white; color: #667eea; border-radius: 6px; cursor: pointer; }
        .format-btn.active { background: #667eea; color: white; }
        .action-buttons { display: flex; gap: 15px; }
        .btn { padding: 15px 30px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; color: white; }
        .btn-info { background: #4facfe; }
        .btn-download { background: #667eea; }
        .btn:hover { opacity: 0.9; }
        .video-info { margin-top: 20px; padding: 20px; background: #f8f9fa; border-radius: 8px; display: none; }
        .loading { text-align: center; padding: 20px; display: none; }
        .error { background: #ffe6e6; color: #d63031; padding: 15px; border-radius: 8px; margin-top: 20px; display: none; }
        .success { background: #e6f7e6; color: #27ae60; padding: 15px; border-radius: 8px; margin-top: 20px; display: none; }
        .status-info { background: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>YouTube API Downloader</h1>
            <p>Download YouTube videos using official API</p>
        </div>
        
        <div class="input-group">
            <input type="url" class="url-input" id="videoUrl" placeholder="Paste YouTube URL here" autocomplete="off">
        </div>
        
        <div class="format-buttons">
            <button class="format-btn active" data-format="best">Best Quality</button>
            <button class="format-btn" data-format="video_720">720p</button>
            <button class="format-btn" data-format="video_480">480p</button>
            <button class="format-btn" data-format="audio">Audio MP3</button>
        </div>
        
        <div class="action-buttons">
            <button class="btn btn-info" onclick="getVideoInfo()">Get Info</button>
            <button class="btn btn-download" onclick="downloadContent()">Download</button>
        </div>
        
        <div class="video-info" id="videoInfo">
            <h3 id="videoTitle"></h3>
            <p id="videoChannel"></p>
            <p id="videoDuration"></p>
        </div>
        
        <div class="loading" id="loading">Loading...</div>
        <div class="error" id="error"></div>
        <div class="success" id="success"></div>
        
        <div class="status-info">
            <strong>API Status:</strong> <span id="statusText">Checking...</span><br>
            <strong>Cookies:</strong> <span id="cookiesStatus">Checking...</span>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;
        let currentFormat = 'best';
        
        document.querySelectorAll('.format-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.format-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                currentFormat = this.dataset.format;
            });
        });
        
        async function checkStatus() {
            try {
                const response = await fetch(API_BASE + '/status');
                const data = await response.json();
                document.getElementById('statusText').textContent = 
                    `YouTube API: ${data.youtube_api}`;
                document.getElementById('cookiesStatus').textContent = 
                    `${data.cookies_available ? '✅ Available' : '❌ Not found'}`;
            } catch (error) {
                document.getElementById('statusText').textContent = 'Service unavailable';
            }
        }
        
        function showLoading(show) {
            document.getElementById('loading').style.display = show ? 'block' : 'none';
        }
        
        function showError(message) {
            document.getElementById('error').textContent = message;
            document.getElementById('error').style.display = 'block';
            document.getElementById('success').style.display = 'none';
        }
        
        function showSuccess(message) {
            document.getElementById('success').textContent = message;
            document.getElementById('success').style.display = 'block';
            document.getElementById('error').style.display = 'none';
        }
        
        function getVideoInfo() {
            const url = document.getElementById('videoUrl').value.trim();
            if (!url) return showError('Please enter URL');
            
            showLoading(true);
            fetch(API_BASE + '/info?url=' + encodeURIComponent(url))
                .then(r => r.json())
                .then(data => {
                    showLoading(false);
                    if (data.error) return showError(data.error);
                    
                    document.getElementById('videoTitle').textContent = data.title;
                    document.getElementById('videoChannel').textContent = 'Channel: ' + data.channel_title;
                    document.getElementById('videoDuration').textContent = 'Duration: ' + data.duration;
                    document.getElementById('videoInfo').style.display = 'block';
                    showSuccess('Video info loaded!');
                })
                .catch(error => {
                    showLoading(false);
                    showError('Error: ' + error.message);
                });
        }
        
        function downloadContent() {
            const url = document.getElementById('videoUrl').value.trim();
            if (!url) return showError('Please enter URL');
            
            showLoading(true);
            const downloadUrl = API_BASE + '/download?url=' + encodeURIComponent(url) + '&format=' + currentFormat;
            
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            iframe.src = downloadUrl;
            document.body.appendChild(iframe);
            
            fetch(downloadUrl)
                .then(response => {
                    showLoading(false);
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Download failed');
                        });
                    }
                    showSuccess('Download started!');
                    setTimeout(() => document.body.removeChild(iframe), 5000);
                })
                .catch(error => {
                    showLoading(false);
                    showError(error.message);
                    document.body.removeChild(iframe);
                });
        }
        
        document.getElementById('videoUrl').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') getVideoInfo();
        });
        
        window.addEventListener('load', checkStatus);
    </script>
</body>
</html>'''
        
        with open(template_path, 'w') as f:
            f.write(html_content)
        logger.info("Created default template file")

# Create template on startup
create_default_template()

@app.route('/')
def home():
    return render_template('index_api.html')

@app.route('/info')
def get_video_info():
    """Get video information using YouTube API"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    video_id = downloader.extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    result = downloader.get_video_info(video_id)
    return jsonify(result)

@app.route('/search')
def search_videos():
    """Search for videos using YouTube API"""
    query = request.args.get('q')
    max_results = request.args.get('max', 10, type=int)
    
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    
    result = downloader.search_videos(query, max_results)
    return jsonify(result)

@app.route('/download')
def download_video():
    """Download video with API verification"""
    url = request.args.get('url')
    format_type = request.args.get('format', 'best')
    
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    video_id = downloader.extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    logger.info(f"Download request: {video_id}, Format: {format_type}")
    
    result = downloader.download_video(video_id, format_type)
    
    if 'error' in result:
        return jsonify(result), 500
    
    try:
        ext = 'mp3' if format_type == 'audio' else result['filename'].split('.')[-1]
        download_name = f"{result['title']}.{ext}"
        
        # Clean filename
        download_name = "".join(c for c in download_name if c.isalnum() or c in ('.', '-', '_'))
        
        return send_file(
            result['filename'],
            as_attachment=True,
            download_name=download_name,
            mimetype='video/mp4' if format_type != 'audio' else 'audio/mpeg'
        )
    except Exception as e:
        logger.error(f"File send error: {e}")
        return jsonify({'error': f'File transfer failed: {str(e)}'}), 500

@app.route('/status')
def status():
    """Check API status"""
    try:
        # Test API with a known video
        test_result = downloader.get_video_info('jNQXAC9IVRw')
        api_status = 'working' if 'error' not in test_result else 'failed'
        api_message = test_result.get('error', 'API is working correctly')
    except Exception as e:
        api_status = 'failed'
        api_message = str(e)
    
    return jsonify({
        'status': 'active',
        'youtube_api': api_status,
        'api_message': api_message,
        'api_key_set': bool(downloader.api_key),
        'cookies_available': os.path.exists(downloader.cookies_file),
        'service': 'YouTube API Downloader'
    })

@app.route('/test')
def test_api():
    """Test API with a known video"""
    test_result = downloader.get_video_info('jNQXAC9IVRw')  # First YouTube video
    return jsonify(test_result)

@app.route('/trending')
def get_trending():
    """Get trending videos"""
    try:
        url = f"{downloader.base_url}/videos"
        params = {
            'part': 'snippet,statistics',
            'chart': 'mostPopular',
            'regionCode': 'US',
            'maxResults': 20,
            'key': downloader.api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        videos = []
        for item in data.get('items', []):
            snippet = item['snippet']
            statistics = item.get('statistics', {})
            
            videos.append({
                'video_id': item['id'],
                'title': snippet['title'],
                'thumbnail': snippet['thumbnails']['high']['url'],
                'channel_title': snippet['channelTitle'],
                'view_count': statistics.get('viewCount', '0'),
                'like_count': statistics.get('likeCount', '0')
            })
        
        return jsonify({'success': True, 'videos': videos})
        
    except Exception as e:
        return jsonify({'error': f'Failed to get trending videos: {str(e)}'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)