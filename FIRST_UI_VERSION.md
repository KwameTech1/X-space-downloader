You are a senior backend engineer and software architect.

We already have a working Twitter/X Spaces downloader engine built in Python.

The existing system includes:

- Space URL parser
- Twitter/X metadata fetcher
- HLS playlist parser
- async segment downloader
- audio merger using ffmpeg
- CLI interface

Example CLI command:

space-downloader https://x.com/i/spaces/SPACE_ID

Your task is to build a Web UI that sits on top of this existing engine.

IMPORTANT:
Do NOT rewrite the downloader.

The Web UI must reuse the existing downloader modules.

--------------------------------------------------

OBJECTIVE

Create a simple but professional web interface where users can download Twitter/X Spaces audio.

The web interface should allow users to:

• paste a Space URL  
• start a download  
• see download progress  
• download the finished audio file  

--------------------------------------------------

TECH STACK

Backend:
Python + FastAPI

Frontend:
HTML
CSS
JavaScript

Optional improvements:
WebSockets for real-time progress updates.

--------------------------------------------------

WEB APPLICATION ARCHITECTURE

Create a web application layer that communicates with the downloader engine.

Example structure:

web_app/
    main.py
    routes.py
    downloader_service.py
    templates/
        index.html
    static/
        styles.css
        script.js

Responsibilities:

main.py
starts the FastAPI server

routes.py
defines API endpoints

downloader_service.py
calls the existing downloader engine

templates/index.html
main web interface

static/script.js
handles frontend interactions

--------------------------------------------------

USER FLOW

1. user opens the web page
2. user pastes a Twitter/X Space URL
3. user clicks "Download"
4. backend calls the downloader engine
5. progress updates appear
6. when finished, the audio file becomes downloadable

--------------------------------------------------

FEATURES

The Web UI should support:

• input field for Space URL
• download button
• progress indicator
• success message
• download link for final file
• error messages if download fails

--------------------------------------------------

IMPLEMENTATION PLAN

Guide me step-by-step to build the Web UI.

For each step include:

- command to run
- file to create
- code to write
- explanation

We will build this in the terminal step-by-step.

--------------------------------------------------

IMPORTANT

Do not rewrite the downloader engine.

Instead import and reuse the existing downloader modules.

Write production-quality Python code and explain design decisions like a senior engineer mentoring a junior developer.