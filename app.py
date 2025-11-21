from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp
import os
import time
import threading
import tempfile
import logging
import traceback

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
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        
        # Verify cookies file exists
        if not os.path.exists(self.cookies_file):
            logger.warning(f"Cookies file '{self.cookies_file}' not found. Downloading without cookies.")
        
    def get_ydl_options(self, format_type='best'):
        """Get yt-dlp options with custom cookies and user agent"""
        
        options = {
            'outtmpl': os.path.join(self.temp_dir, '%(title).100s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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
            },
            'sleep_interval': 2,
            'max_sleep_interval': 5,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'prefer_insecure': False,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'verbose': True,
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
    
    def download_video(self, url, format_type='best'):
        """Download video with enhanced error handling"""
        try:
            logger.info(f"Starting download: {url} with format {format_type}")
            
            options = self.get_ydl_options(format_type)
            
            with yt_dlp.YoutubeDL(options) as ydl:
                # First get info without downloading
                info = ydl.extract_info(url, download=False)
                
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
                result = ydl.extract_info(url, download=True)
                
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
            elif "Sign in" in error_msg:
                return {'error': 'Age-restricted video. Try using cookies.txt with logged-in session.'}
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
        if not ('youtube.com/watch' in url or 'youtu.be/' in url):
            return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        options = downloader.get_ydl_options()
        options['extract_flat'] = False
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            
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
        elif "Sign in" in error_msg or "age restricted" in error_msg.lower():
            return jsonify({'error': 'Age-restricted video. Try using a cookies.txt file with logged-in YouTube session.'}), 403
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
    if not ('youtube.com/watch' in url or 'youtu.be/' in url):
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

@app.route('/audio')
def download_audio():
    """Download audio only endpoint"""
    url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400
    
    # Validate URL
    if not ('youtube.com/watch' in url or 'youtu.be/' in url):
        return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
    
    result = downloader.download_video(url, 'audio')
    
    if 'error' in result:
        return jsonify(result), 500
    
    try:
        download_name = f"{result['title']}.mp3"
        download_name = "".join(c for c in download_name if c.isalnum() or c in ('.', '-', '_'))
        
        return send_file(
            result['filename'],
            as_attachment=True,
            download_name=download_name,
            mimetype='audio/mpeg'
        )
    except Exception as e:
        return jsonify({'error': f'File send failed: {str(e)}'}), 500

@app.route('/status')
def status():
    """Service status endpoint"""
    return jsonify({
        'status': 'active',
        'user_agent': downloader.user_agent,
        'cookies_loaded': os.path.exists(downloader.cookies_file),
        'temp_files': len(os.listdir(downloader.temp_dir)) if os.path.exists(downloader.temp_dir) else 0
    })

# Health check endpoint for Render
@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)