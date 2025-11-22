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
import json

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

class YouTubeIframeDownloader:
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
                'published_at': snippet['publishedAt'][:10],
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
        duration = duration[2:]
        time_parts = []
        
        if 'H' in duration:
            hours, duration = duration.split('H')
            time_parts.append(f"{hours}h")
        
        if 'M' in duration:
            minutes, duration = duration.split('M')
            time_parts.append(f"{minutes}m")
        
        if 'S' in duration:
            seconds = duration.split('S')[0]
            time_parts.append(f"{seconds}s")
        
        return ' '.join(time_parts) if time_parts else 'Unknown'
    
    def get_streaming_data(self, video_id):
        """Get streaming data using YouTube iframe API technique"""
        try:
            # Method 1: Use YouTube iframe API
            embed_url = f"https://www.youtube.com/embed/{video_id}"
            
            # Method 2: Extract from video info page
            info_url = f"https://www.youtube.com/get_video_info?video_id={video_id}"
            response = requests.get(info_url, timeout=10)
            
            if response.status_code == 200:
                # Parse the response to get streaming data
                data = parse_qs(response.text)
                if 'player_response' in data:
                    player_response = json.loads(data['player_response'][0])
                    streaming_data = player_response.get('streamingData', {})
                    
                    formats = streaming_data.get('formats', [])
                    adaptive_formats = streaming_data.get('adaptiveFormats', [])
                    
                    all_formats = formats + adaptive_formats
                    
                    # Filter available formats
                    available_formats = []
                    for fmt in all_formats:
                        if fmt.get('url') or fmt.get('signatureCipher'):
                            quality = fmt.get('qualityLabel', 'unknown')
                            mime_type = fmt.get('mimeType', '')
                            url = fmt.get('url', '')
                            
                            available_formats.append({
                                'quality': quality,
                                'mime_type': mime_type,
                                'url': url,
                                'itag': fmt.get('itag')
                            })
                    
                    return {
                        'success': True,
                        'formats': available_formats,
                        'embed_url': embed_url
                    }
            
            return {'error': 'Could not extract streaming data'}
            
        except Exception as e:
            logger.error(f"Streaming data error: {e}")
            return {'error': f'Failed to get streaming data: {str(e)}'}
    
    def download_via_iframe(self, video_id, format_type='best'):
        """Download using iframe technique and direct streaming URLs"""
        try:
            # Get video info first
            video_info = self.get_video_info(video_id)
            if 'error' in video_info:
                return video_info
            
            # Get streaming data
            streaming_data = self.get_streaming_data(video_id)
            if 'error' in streaming_data:
                return streaming_data
            
            # Try to use yt-dlp with iframe approach
            return self.download_with_ytdlp(video_id, format_type, video_info)
            
        except Exception as e:
            logger.error(f"Iframe download error: {e}")
            return {'error': f'Iframe download failed: {str(e)}'}
    
    def download_with_ytdlp(self, video_id, format_type, video_info):
        """Use yt-dlp with enhanced iframe-like approach"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(self.temp_dir, f'%(title).100s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                # Use embed-like approach
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_embed', 'web_embed'],
                        'player_skip': ['configs'],
                    }
                },
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.youtube.com/',
                    'Origin': 'https://www.youtube.com'
                }
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
                
        except Exception as e:
            logger.error(f"yt-dlp iframe approach failed: {e}")
            return self.provide_embed_solution(video_id, video_info)
    
    def provide_embed_solution(self, video_id, video_info):
        """Provide embed-based solution when direct download fails"""
        try:
            # Create an HTML file with embedded player and download instructions
            html_content = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Download {video_info['title']}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .container {{ max-width: 800px; margin: 0 auto; }}
                    .player {{ margin: 20px 0; }}
                    .instructions {{ background: #f5f5f5; padding: 20px; border-radius: 8px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>{video_info['title']}</h1>
                    <p>Channel: {video_info['channel_title']}</p>
                    
                    <div class="player">
                        <iframe width="100%" height="400" 
                                src="https://www.youtube.com/embed/{video_id}" 
                                frameborder="0" 
                                allowfullscreen>
                        </iframe>
                    </div>
                    
                    <div class="instructions">
                        <h3>Download Options:</h3>
                        <p><strong>Option 1:</strong> Right-click on the video above and select "Save video as..."</p>
                        <p><strong>Option 2:</strong> Use browser extensions like "Video DownloadHelper"</p>
                        <p><strong>Option 3:</strong> Use online YouTube downloader services</p>
                        <p><strong>Direct Links:</strong></p>
                        <ul>
                            <li><a href="https://www.y2mate.com/youtube/{video_id}" target="_blank">Download via y2mate</a></li>
                            <li><a href="https://en.savefrom.net/1-youtube-video-downloader-{video_id}/" target="_blank">Download via SaveFrom</a></li>
                            <li><a href="https://yt5s.com/en{video_id}" target="_blank">Download via YT5s</a></li>
                        </ul>
                    </div>
                </div>
            </body>
            </html>
            '''
            
            # Save as HTML file
            html_filename = os.path.join(self.temp_dir, f'{video_id}_download.html')
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return {
                'success': True,
                'filename': html_filename,
                'title': f"Download_{video_info['title']}",
                'video_id': video_id,
                'embed_solution': True
            }
            
        except Exception as e:
            logger.error(f"Embed solution failed: {e}")
            return {'error': 'All download methods failed. YouTube restrictions prevent downloading.'}

downloader = YouTubeIframeDownloader()

# Background cleanup
def cleanup_old_files():
    while True:
        time.sleep(3600)
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

# Create default template
def create_default_template():
    template_path = 'templates/index_iframe.html'
    if not os.path.exists(template_path):
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Iframe Downloader</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; background: white; border-radius: 15px; padding: 30px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #333; margin-bottom: 10px; }
        .input-group { margin-bottom: 20px; }
        .url-input { width: 100%; padding: 15px; border: 2px solid #ddd; border-radius: 8px; font-size: 16px; }
        .format-buttons { display: flex; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
        .format-btn { padding: 10px 20px; border: 2px solid #667eea; background: white; color: #667eea; border-radius: 6px; cursor: pointer; }
        .format-btn.active { background: #667eea; color: white; }
        .action-buttons { display: flex; gap: 15px; margin-bottom: 20px; }
        .btn { padding: 15px 30px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; color: white; }
        .btn-info { background: #4facfe; }
        .btn-download { background: #667eea; }
        .btn-embed { background: #f093fb; }
        .btn:hover { opacity: 0.9; }
        .video-info { margin-top: 20px; padding: 20px; background: #f8f9fa; border-radius: 8px; display: none; }
        .video-preview { margin: 20px 0; text-align: center; }
        .embed-container { position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; }
        .embed-container iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
        .loading { text-align: center; padding: 20px; display: none; }
        .error { background: #ffe6e6; color: #d63031; padding: 15px; border-radius: 8px; margin-top: 20px; display: none; }
        .success { background: #e6f7e6; color: #27ae60; padding: 15px; border-radius: 8px; margin-top: 20px; display: none; }
        .status-info { background: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 20px; }
        .download-options { margin-top: 20px; padding: 15px; background: #fff3cd; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>YouTube Iframe Downloader</h1>
            <p>Download videos using YouTube's official iframe player</p>
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
            <button class="btn btn-download" onclick="downloadContent()">Direct Download</button>
            <button class="btn btn-embed" onclick="showEmbedSolution()">Embed Solution</button>
        </div>
        
        <div class="video-info" id="videoInfo">
            <h3 id="videoTitle"></h3>
            <p id="videoChannel"></p>
            <p id="videoDuration"></p>
            
            <div class="video-preview" id="videoPreview" style="display: none;">
                <h4>Video Preview:</h4>
                <div class="embed-container" id="embedContainer"></div>
            </div>
        </div>
        
        <div class="download-options" id="downloadOptions" style="display: none;">
            <h4>Alternative Download Methods:</h4>
            <p>If direct download fails, try these methods:</p>
            <ul>
                <li>Right-click the video above and select "Save video as..."</li>
                <li>Use browser extensions like "Video DownloadHelper"</li>
                <li>Use the embed solution button above</li>
            </ul>
        </div>
        
        <div class="loading" id="loading">Loading...</div>
        <div class="error" id="error"></div>
        <div class="success" id="success"></div>
        
        <div class="status-info">
            <strong>API Status:</strong> <span id="statusText">Checking...</span><br>
            <strong>Method:</strong> <span id="methodText">Iframe + YouTube API</span>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;
        let currentFormat = 'best';
        let currentVideoId = null;
        
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
                    `YouTube API: ${data.youtube_api} | Service: ${data.status}`;
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
                    
                    currentVideoId = data.video_id;
                    
                    document.getElementById('videoTitle').textContent = data.title;
                    document.getElementById('videoChannel').textContent = 'Channel: ' + data.channel_title;
                    document.getElementById('videoDuration').textContent = 'Duration: ' + data.duration;
                    document.getElementById('videoInfo').style.display = 'block';
                    
                    // Show embed preview
                    const embedContainer = document.getElementById('embedContainer');
                    embedContainer.innerHTML = `
                        <iframe width="100%" height="400" 
                                src="https://www.youtube.com/embed/${data.video_id}" 
                                frameborder="0" 
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                                allowfullscreen>
                        </iframe>
                    `;
                    document.getElementById('videoPreview').style.display = 'block';
                    document.getElementById('downloadOptions').style.display = 'block';
                    
                    showSuccess('Video info loaded! You can now download or use the embedded player.');
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
            
            // Try direct download first
            fetch(downloadUrl)
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Download failed');
                        });
                    }
                    return response.blob();
                })
                .then(blob => {
                    showLoading(false);
                    if (blob instanceof Blob) {
                        const downloadUrl = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = downloadUrl;
                        a.download = `youtube_video.${currentFormat === 'audio' ? 'mp3' : 'mp4'}`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(downloadUrl);
                        showSuccess('Download started!');
                    }
                })
                .catch(error => {
                    showLoading(false);
                    showError('Direct download failed: ' + error.message);
                    // Suggest embed solution
                    document.getElementById('downloadOptions').style.display = 'block';
                });
        }
        
        function showEmbedSolution() {
            if (!currentVideoId) return showError('Please get video info first');
            
            const embedWindow = window.open('', '_blank');
            embedWindow.document.write(`
                <html>
                <head><title>YouTube Download Helper</title></head>
                <body>
                    <h2>Embed Download Solution</h2>
                    <iframe width="100%" height="400" 
                            src="https://www.youtube.com/embed/${currentVideoId}" 
                            frameborder="0" 
                            allowfullscreen>
                    </iframe>
                    <div style="margin: 20px; padding: 15px; background: #f0f0f0;">
                        <h3>Download Instructions:</h3>
                        <p>1. Right-click on the video above</p>
                        <p>2. Select "Save video as..." (if available)</p>
                        <p>3. Or use browser extensions</p>
                        <p>Alternative services:</p>
                        <ul>
                            <li><a href="https://www.y2mate.com/youtube/${currentVideoId}" target="_blank">y2mate.com</a></li>
                            <li><a href="https://en.savefrom.net/1-youtube-video-downloader-${currentVideoId}/" target="_blank">SaveFrom.net</a></li>
                        </ul>
                    </div>
                </body>
                </html>
            `);
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
        logger.info("Created iframe template file")

create_default_template()

@app.route('/')
def home():
    return render_template('index_iframe.html')

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

@app.route('/download')
def download_video():
    """Download video using iframe technique"""
    url = request.args.get('url')
    format_type = request.args.get('format', 'best')
    
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    video_id = downloader.extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    logger.info(f"Iframe download request: {video_id}, Format: {format_type}")
    
    result = downloader.download_via_iframe(video_id, format_type)
    
    if 'error' in result:
        return jsonify(result), 500
    
    try:
        # Check if it's an embed solution
        if result.get('embed_solution'):
            return send_file(
                result['filename'],
                as_attachment=True,
                download_name=f"{result['title']}.html",
                mimetype='text/html'
            )
        else:
            # Regular file download
            ext = 'mp3' if format_type == 'audio' else result['filename'].split('.')[-1]
            download_name = f"{result['title']}.{ext}"
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
        test_result = downloader.get_video_info('jNQXAC9IVRw')
        api_status = 'working' if 'error' not in test_result else 'failed'
    except Exception as e:
        api_status = 'failed'
    
    return jsonify({
        'status': 'active',
        'youtube_api': api_status,
        'api_key_set': bool(downloader.api_key),
        'method': 'iframe_technique'
    })

@app.route('/embed/<video_id>')
def embed_player(video_id):
    """Direct embed player endpoint"""
    video_info = downloader.get_video_info(video_id)
    title = video_info.get('title', 'YouTube Video') if 'error' not in video_info else 'YouTube Video'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{ margin: 0; padding: 20px; background: #f0f0f0; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>{title}</h2>
            <iframe width="100%" height="450" 
                    src="https://www.youtube.com/embed/{video_id}" 
                    frameborder="0" 
                    allowfullscreen>
            </iframe>
            <div style="margin-top: 20px; padding: 15px; background: #e3f2fd; border-radius: 5px;">
                <h3>Download Options:</h3>
                <p>Right-click the video and select "Save video as..." if available.</p>
                <p>Or use browser extensions for downloading.</p>
            </div>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)