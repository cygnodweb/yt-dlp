from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp
import os
import time
import threading
import tempfile
import logging
import traceback
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB limit for free hosting
CLEANUP_INTERVAL = 3600  # Clean files every hour

class SmartYouTubeDownloader:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cookies_file = "cookies.txt"
        
    def get_simple_options(self, format_type='best'):
        """Simple options that might work better on restricted hosting"""
        options = {
            'outtmpl': os.path.join(self.temp_dir, '%(id)s.%(ext)s'),  # Use video ID instead of title
            'quiet': True,
            'no_warnings': False,
            # Try without cookies first
            # 'cookiefile': self.cookies_file if os.path.exists(self.cookies_file) else None,
            'format': 'worst[height<=360]' if format_type == 'video_360' else 'worst',
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
        }
        
        if format_type == 'audio':
            options.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
            })
        
        return options
    
    def get_advanced_options(self, format_type='best'):
        """Advanced options with cookies for when simple fails"""
        options = {
            'outtmpl': os.path.join(self.temp_dir, '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': False,
            'cookiefile': self.cookies_file,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
            },
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
        }
        
        if format_type == 'audio':
            options.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif format_type == 'video_720':
            options['format'] = 'best[height<=720]'
        elif format_type == 'video_480':
            options['format'] = 'best[height<=480]'
        elif format_type == 'video_360':
            options['format'] = 'best[height<=360]'
        else:
            options['format'] = 'best[height<=480]'
            
        return options
    
    def normalize_url(self, url):
        """Convert various YouTube URLs to standard format"""
        if 'youtube.com/shorts/' in url:
            video_id = url.split('/shorts/')[-1].split('?')[0]
            return f'https://www.youtube.com/watch?v={video_id}'
        elif 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[-1].split('?')[0]
            return f'https://www.youtube.com/watch?v={video_id}'
        return url
    
    def download_video(self, url, format_type='best'):
        """Try multiple strategies to download video"""
        normalized_url = self.normalize_url(url)
        logger.info(f"Attempting download: {normalized_url}")
        
        # Strategy 1: Try simple approach first (no cookies, lower quality)
        logger.info("Trying simple download strategy...")
        try:
            options = self.get_simple_options(format_type)
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(normalized_url, download=True)
                filename = ydl.prepare_filename(info)
                
                if format_type == 'audio':
                    filename = filename.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                
                return {
                    'success': True,
                    'filename': filename,
                    'title': info.get('title', 'video'),
                    'duration': info.get('duration', 0),
                }
        except Exception as e:
            logger.warning(f"Simple strategy failed: {e}")
        
        # Strategy 2: Try with cookies and advanced options
        if os.path.exists(self.cookies_file):
            logger.info("Trying advanced strategy with cookies...")
            try:
                options = self.get_advanced_options(format_type)
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(normalized_url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    if format_type == 'audio':
                        filename = filename.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                    
                    return {
                        'success': True,
                        'filename': filename,
                        'title': info.get('title', 'video'),
                        'duration': info.get('duration', 0),
                    }
            except Exception as e:
                logger.error(f"Advanced strategy failed: {e}")
        
        # Strategy 3: Try external services as fallback
        logger.info("Trying external service fallback...")
        try:
            return self.try_external_service(normalized_url, format_type)
        except Exception as e:
            logger.error(f"External service failed: {e}")
        
        return {'error': 'All download strategies failed. YouTube is blocking requests from this server. Try using a different network or service.'}
    
    def try_external_service(self, url, format_type):
        """Fallback to using external services"""
        # This is a placeholder for external service integration
        # You could integrate with services like:
        # - y2mate, savefrom.net, etc.
        # Or use different YouTube download libraries
        
        raise Exception("External services not implemented")

downloader = SmartYouTubeDownloader()

# Background cleanup
def cleanup_old_files():
    while True:
        time.sleep(CLEANUP_INTERVAL)
        try:
            for filename in os.listdir(downloader.temp_dir):
                filepath = os.path.join(downloader.temp_dir, filename)
                if os.path.isfile(filepath):
                    file_age = time.time() - os.path.getctime(filepath)
                    if file_age > 3600:
                        os.remove(filepath)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/download')
def download_video():
    """Download video endpoint"""
    url = request.args.get('url')
    format_type = request.args.get('format', 'best')
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400
    
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
    
    logger.info(f"Download request: {url}, Format: {format_type}")
    
    result = downloader.download_video(url, format_type)
    
    if 'error' in result:
        return jsonify(result), 500
    
    try:
        # Use video ID as filename for reliability
        ext = 'mp3' if format_type == 'audio' else result['filename'].split('.')[-1]
        download_name = f"video.{ext}"
        
        return send_file(
            result['filename'],
            as_attachment=True,
            download_name=download_name,
            mimetype='video/mp4' if format_type != 'audio' else 'audio/mpeg'
        )
    except Exception as e:
        logger.error(f"File send error: {e}")
        return jsonify({'error': f'Download completed but file transfer failed: {str(e)}'}), 500

@app.route('/status')
def status():
    return jsonify({
        'status': 'active',
        'cookies_available': os.path.exists(downloader.cookies_file),
        'service': 'YouTube Downloader',
        'note': 'Free hosting IPs may be blocked by YouTube'
    })

@app.route('/test')
def test_download():
    """Test with a simple, reliable video"""
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # First YouTube video
    result = downloader.download_video(test_url, 'best')
    return jsonify(result)

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)