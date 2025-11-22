from flask import Flask, request, send_file, jsonify, after_this_request
import yt_dlp
import os
import uuid

app = Flask(__name__)

# YT-DLP Options for MP4 video merging
ytdl_options_base = {
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
    'merge_output_format': 'mp4',
    'restrictfilenames': True,
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
}

@app.route('/download', methods=['GET'])
def download():
    url = request.args.get("url")

    if not url:
        return jsonify({"error": "Missing url parameter"}), 400

    # TEMP directory for Render
    temp_folder = f"/tmp/{uuid.uuid4().hex}"
    os.makedirs(temp_folder, exist_ok=True)

    try:
        ytdl_options = ytdl_options_base.copy()
        ytdl_options["outtmpl"] = os.path.join(temp_folder, "%(title)s.%(ext)s")

        # Download the YouTube video
        with yt_dlp.YoutubeDL(ytdl_options) as ytdl:
            info = ytdl.extract_info(url, download=True)
            filename = ytdl.prepare_filename(info)

        # yt-dlp may convert to mp4 after merging
        base = os.path.splitext(filename)[0]
        final_mp4 = base + ".mp4"

        if os.path.exists(final_mp4):
            filename = final_mp4

        if not os.path.exists(filename):
            return jsonify({"error": "File missing after download"}), 500

        # Cleanup AFTER sending file
        @after_this_request
        def cleanup(response):
            try:
                for f in os.listdir(temp_folder):
                    os.remove(os.path.join(temp_folder, f))
                os.rmdir(temp_folder)
            except:
                pass
            return response

        return send_file(filename, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
