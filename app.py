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
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB limit for free hosting
CLEANUP_INTERVAL = 3600  # Clean files every hour

class AdvancedYouTubeDownloader:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cookies_file = "cookies.txt"
        
        # Enhanced user agents with more variety
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
        ]
        
        # Verify cookies file exists
        if not os.path.exists(self.cookies_file):
            logger.warning(f"Cookies file '{self.cookies_file}' not found. Downloading without cookies.")
        else:
            logger.info(f"Cookies file found with {len(open(self.cookies_file).readlines())} lines")
        
    def get_random_headers(self):
        """Generate random browser-like headers"""
        user_agent = random.choice(self.user_agents)
        
        # Different Chrome versions for sec-ch-ua
        chrome_versions = [
            '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"'
        ]
        
        return {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': random.choice(chrome_versions),
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }
    
    def get_ydl_options(self, format_type='best'):
        """Get yt-dlp options with enhanced anti-detection measures"""
        
        options = {
            'outtmpl': os.path.join(self.temp_dir, '%(title).100s.%(ext)s'),
            'quiet': True,
            'no_warnings': False,
            'extract_flat': False,
            'http_headers': self.get_random_headers(),
            'sleep_interval': random.randint(3, 7),
            'max_sleep_interval': 10,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'prefer_insecure': False,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'verbose': False,
            # Enhanced extractor settings
            'extractor_retries': 3,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'keep_fragments': True,
            # YouTube specific settings
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['configs', 'webpage'],
                    'skip': ['dash', 'hls'],
                }
            },
            'postprocessor_args': {
                'sponsorblock': ['--remove', 'all'],
            },
            # Throttling to appear more human
            'throttled_rate': '512K',
            'buffer_size': 1024 * 16,
        }
        
        # Add cookies if file exists
        if os.path.exists(self.cookies_file):
            options['cookiefile'] = self.cookies_file
            logger.info("Using cookies from cookies.txt")
        
        # Format specific options
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
            options.update({
                'format': 'best[height<=720]/best[height<=720]',
            })
        elif format_type == 'video_480':
            options.update({
                'format': 'best[height<=480]/best[height<=480]',
            })
        elif format_type == 'video_360':
            options.update({
                'format': 'best[height<=360]/best[height<=360]',
            })
        else:  # best
            options.update({
                'format': 'best[height<=720]/best',
            })
            
        return options
    
    def normalize_youtube_url(self, url):
        """Convert YouTube Shorts URLs to regular watch URLs"""
        if 'youtube.com/shorts/' in url:
            # Extract video ID from shorts URL
            video_id = url.split('/shorts/')[-1].split('?')[0]
            return f'https://www.youtube.com/watch?v={video_id}'
        elif 'youtu.be/' in url:
            # Extract video ID from youtu.be URL
            video_id = url.split('youtu.be/')[-1].split('?')[0]
            return f'https://www.youtube.com/watch?v={video_id}'
        return url
    
    def test_cookies(self):
        """Test if cookies are working"""
        try:
            test_url = "https://www.youtube.com"
            options = {
                'cookiefile': self.cookies_file,
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                # Try to extract a simple video
                info = ydl.extract_info("https://www.youtube.com/watch?v=jNQXAC9IVRw", download=False, process=False)
                return info is not None
        except:
            return False
    
    def download_video(self, url, format_type='best'):
        """Download video with enhanced error handling and URL normalization"""
        try:
            # Normalize URL first
            normalized_url = self.normalize_youtube_url(url)
            logger.info(f"Starting download - Original: {url}, Normalized: {normalized_url}, Format: {format_type}")
            
            # Test cookies first
            if os.path.exists(self.cookies_file):
                cookies_working = self.test_cookies()
                logger.info(f"Cookies test: {'Working' if cookies_working else 'Not working'}")
            
            options = self.get_ydl_options(format_type)
            
            # Add random delay to mimic human behavior
            time.sleep(random.uniform(2, 5))
            
            with yt_dlp.YoutubeDL(options) as ydl:
                # First get info without downloading
                try:
                    info = ydl.extract_info(normalized_url, download=False, process=False)
                except Exception as e:
                    logger.warning(f"Initial info extraction failed, retrying with process=True: {e}")
                    # Try with process=True for some videos
                    info = ydl.extract_info(normalized_url, download=False)
                
                if not info:
                    return {'error': 'Could not extract video information - video may be private, age-restricted, or unavailable'}
                
                # Check file size
                filesize = info.get('filesize') or info.get('filesize_approx')
                if filesize and filesize > MAX_FILE_SIZE:
                    return {'error': f'File too large ({filesize//1024//1024}MB). Maximum allowed: {MAX_FILE_SIZE//1024//1024}MB'}
                
                # Check duration (optional - limit to 2 hours for free tier)
                duration = info.get('duration', 0)
                if duration > 7200:  # 2 hours
                    return {'error': 'Video too long (max 2 hours allowed)'}
                
                # Download the video
                logger.info(f"Starting actual download for: {info.get('title', 'Unknown')}")
                result = ydl.extract_info(normalized_url, download=True)
                
                filename = ydl.prepare_filename(result)
                if format_type == 'audio':
                    filename = filename.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                
                # Clean filename
                safe_title = "".join(c for c in result.get('title', 'video') if c.isalnum() or c in (' ', '-', '_')).rstrip()
                
                return {
                    'success': True,
                    'filename': filename,
                    'title': safe_title,
                    'duration': result.get('duration', 0),
                    'thumbnail': result.get('thumbnail', ''),
                    'uploader': result.get('uploader', ''),
                    'view_count': result.get('view_count', 0),
                    'description': result.get('description', '')[:200] + '...' if result.get('description') else ''
                }
                
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Download error: {e}")
            error_msg = str(e)
            if "Private video" in error_msg:
                return {'error': 'This is a private video. Cannot download.'}
            elif "Sign in" in error_msg or "bot" in error_msg.lower():
                return {'error': 'YouTube is blocking automated requests. This is common on free hosting services. Try: 1) Using a different video 2) Waiting a few minutes 3) Using a different network'}
            elif "Video unavailable" in error_msg:
                return {'error': 'Video is unavailable or removed.'}
            else:
                return {'error': f'Download failed: {error_msg}'}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.error(traceback.format_exc())
            return {'error': f'Unexpected error: {str(e)}'}

downloader = AdvancedYouTubeDownloader()

# Background cleanup thread
def cleanup_old_files():
    while True:
        time.sleep(CLEANUP_INTERVAL)
        try:
            for filename in os.listdir(downloader.temp_dir):
                filepath = os.path.join(downloader.temp_dir, filename)
                if os.path.isfile(filepath):
                    file_age = time.time() - os.path.getctime(filepath)
                    if file_age > 3600:  # Delete files older than 1 hour
                        os.remove(filepath)
                        logger.info(f"Cleaned up old file: {filename}")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/info')
def get_video_info():
    """Get video information without downloading"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    try:
        # Validate URL
        if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
            return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        # Normalize URL
        normalized_url = downloader.normalize_youtube_url(url)
        
        options = downloader.get_ydl_options()
        options['extract_flat'] = False
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(normalized_url, download=False)
            
            if not info:
                return jsonify({'error': 'Could not fetch video information. The video may be private, age-restricted, or unavailable.'}), 404
            
            # Get available formats
            formats = []
            for f in info.get('formats', []):
                if f.get('filesize') or f.get('format_note'):
                    formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext'),
                        'quality': f.get('format_note', 'unknown'),
                        'filesize': f.get('filesize', 0),
                        'height': f.get('height'),
                        'width': f.get('width')
                    })
            
            return jsonify({
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': formats[:10]  # Limit to first 10 formats
            })
            
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"Info extraction error: {error_msg}")
        
        if "Private video" in error_msg:
            return jsonify({'error': 'This is a private video. Cannot access.'}), 403
        elif "Sign in" in error_msg or "age restricted" in error_msg.lower() or "bot" in error_msg.lower():
            return jsonify({'error': 'YouTube is blocking automated requests. This is common on free hosting. Try using a different video or network.'}), 403
        elif "Video unavailable" in error_msg:
            return jsonify({'error': 'Video is unavailable or has been removed.'}), 404
        else:
            return jsonify({'error': f'Failed to get video info: {error_msg}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in info: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to get video information: {str(e)}'}), 500

@app.route('/download')
def download_video():
    """Download video endpoint with query parameters"""
    url = request.args.get('url')
    format_type = request.args.get('format', 'best')
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400
    
    # Validate URL
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
    
    # Validate format
    valid_formats = ['best', 'audio', 'video_720', 'video_480', 'video_360']
    if format_type not in valid_formats:
        return jsonify({'error': f'Invalid format. Use: {", ".join(valid_formats)}'}), 400
    
    logger.info(f"Download request - URL: {url}, Format: {format_type}")
    
    result = downloader.download_video(url, format_type)
    
    if 'error' in result:
        return jsonify(result), 500
    
    try:
        # Get file extension
        ext = 'mp3' if format_type == 'audio' else result['filename'].split('.')[-1]
        download_name = f"{result['title']}.{ext}"
        
        # Clean download name
        download_name = "".join(c for c in download_name if c.isalnum() or c in ('.', '-', '_'))
        
        return send_file(
            result['filename'],
            as_attachment=True,
            download_name=download_name,
            mimetype='video/mp4' if format_type != 'audio' else 'audio/mpeg'
        )
    except Exception as e:
        logger.error(f"File send error: {e}")
        return jsonify({'error': f'File send failed: {str(e)}'}), 500

@app.route('/status')
def status():
    """Service status endpoint"""
    cookies_working = downloader.test_cookies() if os.path.exists(downloader.cookies_file) else False
    return jsonify({
        'status': 'active',
        'cookies_loaded': os.path.exists(downloader.cookies_file),
        'cookies_working': cookies_working,
        'temp_files': len(os.listdir(downloader.temp_dir)) if os.path.exists(downloader.temp_dir) else 0
    })

# Health check endpoint for Render
@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

# Test endpoint with a known working video
@app.route('/test')
def test_download():
    """Test endpoint with a known working video"""
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # First YouTube video
    result = downloader.download_video(test_url, 'best')
    return jsonify(result)

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)