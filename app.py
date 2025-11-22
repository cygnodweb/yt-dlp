from flask import Flask, request, jsonify, send_file, render_template, Response
from flask_cors import CORS
import requests
import os
import tempfile
import logging
import threading
import time
from urllib.parse import urlparse, parse_qs, unquote
import yt_dlp
import json
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', 'AIzaSyBRoWTktLPtebrpk5l41xnREXtC9Oa2rag')
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# Ensure templates directory exists
os.makedirs('templates', exist_ok=True)

class YouTubeStreamExtractor:
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
    
    def extract_stream_urls(self, video_id):
        """Extract direct stream URLs from YouTube"""
        try:
            # Method 1: Use yt-dlp to get stream information
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'listformats': True,
            }
            
            streams = []
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
                
                if 'formats' in info:
                    for fmt in info['formats']:
                        if fmt.get('url'):
                            stream_info = {
                                'format_id': fmt.get('format_id'),
                                'ext': fmt.get('ext', 'unknown'),
                                'quality': fmt.get('format_note', 'unknown'),
                                'resolution': f"{fmt.get('width', '')}x{fmt.get('height', '')}",
                                'filesize': fmt.get('filesize', 0),
                                'url': fmt.get('url'),
                                'vcodec': fmt.get('vcodec', 'none'),
                                'acodec': fmt.get('acodec', 'none')
                            }
                            streams.append(stream_info)
            
            # Filter and categorize streams
            video_streams = [s for s in streams if s['vcodec'] != 'none']
            audio_streams = [s for s in streams if s['acodec'] != 'none' and s['vcodec'] == 'none']
            
            return {
                'success': True,
                'video_streams': video_streams[:10],  # Limit to first 10
                'audio_streams': audio_streams[:5],   # Limit to first 5
                'total_streams': len(streams)
            }
            
        except Exception as e:
            logger.error(f"Stream extraction error: {e}")
            return {'error': f'Failed to extract stream URLs: {str(e)}'}
    
    def download_from_stream(self, video_id, format_id, format_type='video'):
        """Download video from direct stream URL"""
        try:
            # Get video info for title
            video_info = self.get_video_info(video_id)
            if 'error' in video_info:
                return video_info
            
            # Get stream URLs
            streams_info = self.extract_stream_urls(video_id)
            if 'error' in streams_info:
                return streams_info
            
            # Find the requested format
            target_streams = streams_info['video_streams'] if format_type == 'video' else streams_info['audio_streams']
            target_stream = None
            
            if format_id == 'best':
                # Get the best quality stream
                target_stream = target_streams[0] if target_streams else None
            else:
                # Find specific format
                for stream in target_streams:
                    if stream['format_id'] == format_id:
                        target_stream = stream
                        break
            
            if not target_stream:
                return {'error': 'Requested format not available'}
            
            # Download the stream
            stream_url = target_stream['url']
            logger.info(f"Downloading from stream: {stream_url[:100]}...")
            
            # Set appropriate filename and extension
            if format_type == 'audio':
                extension = 'mp3'
                mime_type = 'audio/mpeg'
            else:
                extension = target_stream.get('ext', 'mp4')
                mime_type = 'video/mp4'
            
            filename = f"{video_info['title']}.{extension}"
            safe_filename = "".join(c for c in filename if c.isalnum() or c in ('.', '-', '_'))
            filepath = os.path.join(self.temp_dir, safe_filename)
            
            # Download the stream content
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com'
            }
            
            response = requests.get(stream_url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            # Save to file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return {
                'success': True,
                'filename': filepath,
                'title': video_info['title'],
                'format': target_stream['quality'],
                'stream_url': stream_url
            }
            
        except Exception as e:
            logger.error(f"Stream download error: {e}")
            return {'error': f'Stream download failed: {str(e)}'}
    
    def get_download_options(self, video_id):
        """Get available download options for a video"""
        streams_info = self.extract_stream_urls(video_id)
        if 'error' in streams_info:
            return streams_info
        
        video_options = []
        audio_options = []
        
        # Video options
        for stream in streams_info.get('video_streams', [])[:8]:
            video_options.append({
                'id': stream['format_id'],
                'quality': stream['quality'],
                'resolution': stream['resolution'],
                'size': self.format_size(stream.get('filesize', 0)),
                'type': 'video'
            })
        
        # Audio options
        for stream in streams_info.get('audio_streams', [])[:3]:
            audio_options.append({
                'id': stream['format_id'],
                'quality': stream['quality'],
                'size': self.format_size(stream.get('filesize', 0)),
                'type': 'audio'
            })
        
        return {
            'success': True,
            'video_options': video_options,
            'audio_options': audio_options
        }
    
    def format_size(self, size_bytes):
        """Format file size in human-readable format"""
        if not size_bytes:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

downloader = YouTubeStreamExtractor()

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
    template_path = 'templates/index_stream.html'
    if not os.path.exists(template_path):
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Stream Downloader</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; padding: 30px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #333; margin-bottom: 10px; }
        .input-group { margin-bottom: 20px; }
        .url-input { width: 100%; padding: 15px; border: 2px solid #ddd; border-radius: 8px; font-size: 16px; }
        .action-buttons { display: flex; gap: 15px; margin-bottom: 20px; }
        .btn { padding: 12px 24px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; color: white; }
        .btn-info { background: #4facfe; }
        .btn-download { background: #667eea; }
        .btn:hover { opacity: 0.9; }
        
        .video-info { margin-top: 20px; padding: 20px; background: #f8f9fa; border-radius: 8px; display: none; }
        .video-preview { margin: 20px 0; text-align: center; }
        .embed-container { position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; }
        .embed-container iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
        
        .download-options { margin-top: 20px; display: none; }
        .options-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top: 15px; }
        .option-card { padding: 15px; border: 2px solid #e0e0e0; border-radius: 8px; cursor: pointer; transition: all 0.3s; }
        .option-card:hover { border-color: #667eea; background: #f0f4ff; }
        .option-card.selected { border-color: #667eea; background: #667eea; color: white; }
        .option-quality { font-weight: bold; font-size: 16px; }
        .option-details { font-size: 14px; color: #666; margin-top: 5px; }
        .option-card.selected .option-details { color: #e0e0e0; }
        
        .download-section { margin-top: 20px; padding: 20px; background: #e8f5e8; border-radius: 8px; display: none; }
        .download-btn { background: #28a745; color: white; padding: 15px 30px; border: none; border-radius: 8px; font-size: 18px; cursor: pointer; width: 100%; }
        .download-btn:hover { background: #218838; }
        .download-btn:disabled { background: #6c757d; cursor: not-allowed; }
        
        .loading { text-align: center; padding: 20px; display: none; }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #667eea; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        .error { background: #ffe6e6; color: #d63031; padding: 15px; border-radius: 8px; margin-top: 20px; display: none; }
        .success { background: #e6f7e6; color: #27ae60; padding: 15px; border-radius: 8px; margin-top: 20px; display: none; }
        .status-info { background: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 20px; }
        
        .tab-buttons { display: flex; margin-bottom: 20px; border-bottom: 2px solid #e0e0e0; }
        .tab-btn { padding: 12px 24px; border: none; background: none; cursor: pointer; font-size: 16px; border-bottom: 3px solid transparent; }
        .tab-btn.active { border-bottom: 3px solid #667eea; color: #667eea; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>YouTube Stream Downloader</h1>
            <p>Extract and download videos directly from YouTube streams</p>
        </div>
        
        <div class="input-group">
            <input type="url" class="url-input" id="videoUrl" placeholder="Paste YouTube URL here and press Enter" autocomplete="off">
        </div>
        
        <div class="action-buttons">
            <button class="btn btn-info" onclick="getVideoInfo()">Get Video Info</button>
        </div>
        
        <div class="video-info" id="videoInfo">
            <h3 id="videoTitle"></h3>
            <p id="videoChannel"></p>
            <p id="videoDuration"></p>
            
            <div class="video-preview" id="videoPreview">
                <h4>Video Preview:</h4>
                <div class="embed-container" id="embedContainer"></div>
            </div>
        </div>
        
        <div class="download-options" id="downloadOptions">
            <div class="tab-buttons">
                <button class="tab-btn active" onclick="showVideoOptions()">Video Formats</button>
                <button class="tab-btn" onclick="showAudioOptions()">Audio Formats</button>
            </div>
            
            <div id="videoOptions" class="options-grid"></div>
            <div id="audioOptions" class="options-grid" style="display: none;"></div>
        </div>
        
        <div class="download-section" id="downloadSection">
            <h4>Ready to Download</h4>
            <p>Selected: <span id="selectedFormat">None</span></p>
            <button class="download-btn" onclick="startDownload()" id="downloadBtn">Download Now</button>
        </div>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p id="loadingText">Processing your request...</p>
        </div>
        
        <div class="error" id="error"></div>
        <div class="success" id="success"></div>
        
        <div class="status-info">
            <strong>API Status:</strong> <span id="statusText">Checking...</span><br>
            <strong>Method:</strong> <span>Direct Stream Extraction</span>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;
        let currentVideoId = null;
        let currentVideoInfo = null;
        let selectedFormat = null;
        
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
        
        function showLoading(show, text = 'Processing your request...') {
            document.getElementById('loading').style.display = show ? 'block' : 'none';
            document.getElementById('loadingText').textContent = text;
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
            if (!url) return showError('Please enter a YouTube URL');
            
            showLoading(true, 'Extracting video information...');
            fetch(API_BASE + '/info?url=' + encodeURIComponent(url))
                .then(r => r.json())
                .then(data => {
                    if (data.error) {
                        showLoading(false);
                        showError(data.error);
                        return;
                    }
                    
                    currentVideoId = data.video_id;
                    currentVideoInfo = data;
                    
                    // Display video info
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
                    
                    // Get download options
                    getDownloadOptions();
                })
                .catch(error => {
                    showLoading(false);
                    showError('Error: ' + error.message);
                });
        }
        
        function getDownloadOptions() {
            showLoading(true, 'Extracting available streams...');
            fetch(API_BASE + '/streams/' + currentVideoId)
                .then(r => r.json())
                .then(data => {
                    showLoading(false);
                    if (data.error) {
                        showError(data.error);
                        return;
                    }
                    
                    displayVideoOptions(data.video_options);
                    displayAudioOptions(data.audio_options);
                    
                    document.getElementById('downloadOptions').style.display = 'block';
                    showSuccess('Streams extracted successfully! Select a format to download.');
                })
                .catch(error => {
                    showLoading(false);
                    showError('Error extracting streams: ' + error.message);
                });
        }
        
        function displayVideoOptions(options) {
            const container = document.getElementById('videoOptions');
            container.innerHTML = '';
            
            options.forEach(option => {
                const card = document.createElement('div');
                card.className = 'option-card';
                card.onclick = () => selectFormat(option);
                card.innerHTML = `
                    <div class="option-quality">${option.quality}</div>
                    <div class="option-details">
                        ${option.resolution} | ${option.size}
                    </div>
                `;
                container.appendChild(card);
            });
        }
        
        function displayAudioOptions(options) {
            const container = document.getElementById('audioOptions');
            container.innerHTML = '';
            
            options.forEach(option => {
                const card = document.createElement('div');
                card.className = 'option-card';
                card.onclick = () => selectFormat(option);
                card.innerHTML = `
                    <div class="option-quality">${option.quality}</div>
                    <div class="option-details">
                        Audio | ${option.size}
                    </div>
                `;
                container.appendChild(card);
            });
        }
        
        function showVideoOptions() {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('videoOptions').style.display = 'grid';
            document.getElementById('audioOptions').style.display = 'none';
        }
        
        function showAudioOptions() {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('videoOptions').style.display = 'none';
            document.getElementById('audioOptions').style.display = 'grid';
        }
        
        function selectFormat(option) {
            // Remove selection from all cards
            document.querySelectorAll('.option-card').forEach(card => {
                card.classList.remove('selected');
            });
            
            // Add selection to clicked card
            event.target.closest('.option-card').classList.add('selected');
            
            selectedFormat = option;
            document.getElementById('selectedFormat').textContent = 
                `${option.quality} (${option.type}) - ${option.size}`;
            
            document.getElementById('downloadSection').style.display = 'block';
            document.getElementById('downloadBtn').disabled = false;
        }
        
        function startDownload() {
            if (!selectedFormat || !currentVideoId) {
                showError('Please select a format first');
                return;
            }
            
            showLoading(true, 'Preparing download...');
            
            const downloadUrl = `${API_BASE}/download-stream/${currentVideoId}?format_id=${selectedFormat.id}&type=${selectedFormat.type}`;
            
            // Create hidden iframe for download
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            iframe.src = downloadUrl;
            document.body.appendChild(iframe);
            
            // Also track the download progress
            fetch(downloadUrl)
                .then(response => {
                    showLoading(false);
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Download failed');
                        });
                    }
                    return response.blob();
                })
                .then(blob => {
                    if (blob instanceof Blob) {
                        // Create download link
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `${currentVideoInfo.title}.${selectedFormat.type === 'audio' ? 'mp3' : 'mp4'}`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(url);
                        
                        showSuccess('Download completed successfully!');
                    }
                })
                .catch(error => {
                    showLoading(false);
                    showError('Download failed: ' + error.message);
                })
                .finally(() => {
                    // Remove iframe after a delay
                    setTimeout(() => {
                        if (document.body.contains(iframe)) {
                            document.body.removeChild(iframe);
                        }
                    }, 5000);
                });
        }
        
        // Enter key support
        document.getElementById('videoUrl').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                getVideoInfo();
            }
        });
        
        window.addEventListener('load', checkStatus);
    </script>
</body>
</html>'''
        
        with open(template_path, 'w') as f:
            f.write(html_content)
        logger.info("Created stream extraction template")

create_default_template()

@app.route('/')
def home():
    return render_template('index_stream.html')

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

@app.route('/streams/<video_id>')
def get_stream_options(video_id):
    """Get available stream options for a video"""
    result = downloader.get_download_options(video_id)
    return jsonify(result)

@app.route('/download-stream/<video_id>')
def download_from_stream(video_id):
    """Download video from direct stream"""
    format_id = request.args.get('format_id', 'best')
    stream_type = request.args.get('type', 'video')
    
    logger.info(f"Stream download request: {video_id}, Format: {format_id}, Type: {stream_type}")
    
    result = downloader.download_from_stream(video_id, format_id, stream_type)
    
    if 'error' in result:
        return jsonify(result), 500
    
    try:
        # Determine file extension and MIME type
        if stream_type == 'audio':
            extension = 'mp3'
            mime_type = 'audio/mpeg'
        else:
            extension = 'mp4'
            mime_type = 'video/mp4'
        
        download_name = f"{result['title']}.{extension}"
        download_name = "".join(c for c in download_name if c.isalnum() or c in ('.', '-', '_'))
        
        return send_file(
            result['filename'],
            as_attachment=True,
            download_name=download_name,
            mimetype=mime_type
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
        'method': 'direct_stream_extraction'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)