FROM node:20-bullseye

# Install yt-dlp and ffmpeg
RUN apt-get update && apt-get install -y python3-pip ffmpeg && \
    pip3 install yt-dlp && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json* /app/
RUN npm install --production

COPY . /app
RUN mkdir -p /app/public/downloads
EXPOSE 3000
CMD ["node", "index.js"]
