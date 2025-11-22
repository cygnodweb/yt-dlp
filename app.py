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

class YouTubeAPIDownloader:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.api_key = YOUTUBE_API_KEY
        self.base_url = "https://www.googleapis.com/youtube/v3"
        
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
        """Download video using yt-dlp with API verification"""
        try:
            # First verify video exists using API
            video_info = self.get_video_info(video_id)
            if 'error' in video_info:
                return video_info
            
            logger.info(f"Downloading video: {video_info['title']}")
            
            # Configure yt-dlp options
            ydl_opts = {
                'outtmpl': os.path.join(self.temp_dir, f'%(title).100s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
            }
            
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
            return {'error': f'Download failed: {str(e)}'}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {'error': f'Unexpected error: {str(e)}'}

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
        'service': 'YouTube API Downloader'
    })

@app.route('/test')
def test_api():
    """Test API with a known video"""
    test_result = downloader.get_video_info('jNQXAC9IVRw')  # First YouTube video
    return jsonify(test_result)

# New endpoint to get trending videos
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
    os.makedirs('templates', exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)