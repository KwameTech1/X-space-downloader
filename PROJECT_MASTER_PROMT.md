You are a senior software engineer and reverse‑engineering expert.

Your task is to help me build the most professional, reliable, and developer‑friendly Twitter/X Spaces downloader ever created.

Think like a production engineer building a real tool used by thousands of developers.

The tool must be:
- Reliable
- Cleanly architected
- Easy to install
- Cross‑platform
- Fast
- Well documented

The downloader should allow a user to input a Twitter/X Space URL and download the Space audio as a single file.

--------------------------------------------------
PROJECT GOAL
--------------------------------------------------

Build a professional command line tool that downloads Twitter/X Spaces audio.

Example usage:

space-downloader https://x.com/i/spaces/1LyxBxyzABC

Output:

space_1LyxBxyzABC.mp3


--------------------------------------------------
TECHNICAL REQUIREMENTS
--------------------------------------------------

Preferred language:
Python

Use high quality libraries when appropriate.

Possible libraries:
- requests
- aiohttp
- ffmpeg
- m3u8
- rich (for CLI UI)
- typer (for CLI commands)

Architecture must be modular and production quality.

--------------------------------------------------
CORE FEATURES
--------------------------------------------------

1. Parse Space URL
Extract the Space ID from URLs like:

https://x.com/i/spaces/SPACE_ID

2. Fetch Space Metadata
Use Twitter/X API endpoints or reverse‑engineered endpoints to retrieve metadata.

Metadata should include:
- title
- host
- start time
- replay availability
- audio stream URL

3. Locate HLS Stream
Find the .m3u8 playlist that contains the audio segments.

4. Download Audio Segments
Download all segments efficiently.

Requirements:
- parallel downloads
- retry failed segments
- progress bar

5. Merge Segments
Use ffmpeg to merge all audio segments into one file.

Output formats:
- mp3
- m4a
- wav

6. Metadata Tagging
Embed metadata into the audio file:

- title
- host
- date
- Space URL

7. Progress Feedback
Provide a professional CLI interface showing:

- download progress
- segment count
- speed
- errors

Use the "rich" library for visual feedback.

--------------------------------------------------
ADVANCED FEATURES
--------------------------------------------------

Implement advanced capabilities:

• Resume interrupted downloads
• Download very large Spaces
• Handle Spaces longer than 4 hours
• Automatic retry logic
• Automatic cleanup of temporary files
• Option to save raw segments
• Option to download only a portion of the Space

CLI example:

space-downloader download SPACE_URL
space-downloader info SPACE_URL
space-downloader list-segments SPACE_URL

--------------------------------------------------
PERFORMANCE
--------------------------------------------------

The tool must:

- use async downloads
- handle thousands of segments
- avoid unnecessary API calls
- be memory efficient

--------------------------------------------------
ERROR HANDLING
--------------------------------------------------

Handle cases such as:

- Space not found
- Space still live
- replay not available
- network failure
- incomplete segments

Errors must be clearly explained to the user.

--------------------------------------------------
PROJECT STRUCTURE
--------------------------------------------------

Use a clean architecture:

space_downloader/
    cli.py
    downloader.py
    twitter_api.py
    hls_parser.py
    segment_downloader.py
    audio_merger.py
    metadata.py
    utils.py

Include:

requirements.txt
README.md
example commands

--------------------------------------------------
INSTALLATION
--------------------------------------------------

Make installation simple:

pip install space-downloader

or

git clone repo
pip install -r requirements.txt

--------------------------------------------------
TESTING
--------------------------------------------------

Include basic tests to verify:

- URL parsing
- playlist parsing
- segment downloading

--------------------------------------------------
DELIVERABLES
--------------------------------------------------

Generate the following in order:

1. High level architecture explanation
2. Project folder structure
3. Implementation plan
4. Full source code for each file
5. Installation guide
6. Usage examples
7. Future improvements

--------------------------------------------------
IMPORTANT
--------------------------------------------------

Write production-quality code.

Avoid hacks.

Explain key design decisions like a senior engineer mentoring a junior developer.