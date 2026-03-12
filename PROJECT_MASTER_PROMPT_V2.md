You are a senior backend engineer, distributed systems architect, and reverse engineering expert.

You previously helped design a professional Twitter/X Spaces downloader.

Now we are building VERSION 2 of the system.

Version 2 upgrades the downloader into an automated platform that discovers, downloads, analyzes, and archives Twitter/X Spaces.

IMPORTANT:
This version must build ON TOP of the existing downloader architecture.

Do not redesign everything from scratch.

Instead, extend the system with new modules and services.

Work step-by-step like a senior engineer guiding a production system upgrade.

--------------------------------------------------

EXISTING SYSTEM (VERSION 1)

The current system already includes:

• Space URL parser
• Twitter/X metadata fetcher
• HLS playlist parser
• async segment downloader
• audio merger using ffmpeg
• CLI interface

Example command:

space-downloader https://x.com/i/spaces/SPACE_ID

The downloader can:

• fetch metadata
• download audio segments
• merge segments into a single file
• export mp3
• show progress
• handle retries and errors

This architecture must remain the foundation.

--------------------------------------------------

VERSION 2 OBJECTIVE

Transform the downloader into an automated Twitter/X Spaces intelligence system.

The upgraded system should:

1. Automatically detect new Spaces
2. Automatically download Spaces
3. Transcribe audio into text
4. Generate AI summaries
5. Detect and label speakers
6. Store everything in a searchable archive

--------------------------------------------------

FEATURE 1 — AUTO SPACE DETECTION

Design a module that automatically detects new Spaces.

Capabilities:

• monitor Twitter/X for live Spaces
• detect when a Space starts
• collect the Space ID
• trigger automatic download once replay becomes available

Possible implementation ideas:

• polling Twitter endpoints
• monitoring specific accounts
• scheduled scanning

Create a new service module:

space_monitor/
    space_scanner.py
    scheduler.py
    event_listener.py

Explain how the detection system should work reliably.

--------------------------------------------------

FEATURE 2 — AUTOMATIC TRANSCRIPTION

After a Space is downloaded, automatically generate a transcript.

Use speech-to-text models.

Possible technologies:

• Whisper models
• other open source speech recognition systems

Requirements:

• handle long Spaces (2–4 hours)
• segment transcript by timestamp
• produce clean readable transcripts

Create module:

transcription/
    transcriber.py
    transcript_processor.py

--------------------------------------------------

FEATURE 3 — AI SUMMARIES

Generate summaries from transcripts.

The system should produce:

• short summary
• key topics discussed
• bullet point insights
• important quotes

Create module:

analysis/
    summarizer.py
    topic_extractor.py

--------------------------------------------------

FEATURE 4 — SPEAKER DETECTION

Implement speaker diarization.

The system should:

• detect different speakers
• label them in the transcript
• align speakers with timestamps

Create module:

speaker_detection/
    diarizer.py

--------------------------------------------------

FEATURE 5 — SEARCHABLE ARCHIVE

Create a database system that stores:

• Space metadata
• audio file
• transcript
• summaries
• speaker segments

Design a searchable archive.

Users should be able to search:

• keywords
• topics
• speakers
• phrases said in Spaces

Possible technologies:

PostgreSQL
vector database
semantic search

Create module:

archive/
    database.py
    search_engine.py
    indexing.py

--------------------------------------------------

SYSTEM ARCHITECTURE

Design the upgraded system architecture.

Possible services:

• Space discovery service
• downloader worker
• transcription worker
• AI analysis worker
• archive database
• search index

Explain how these services communicate.

--------------------------------------------------

IMPLEMENTATION PLAN

Create a clear development roadmap.

Break the upgrade into small implementation steps.

For each step include:

• command to run
• file to create
• code to write
• explanation

--------------------------------------------------

IMPORTANT

Do NOT jump directly into full implementation.

Start by:

1. Reviewing the Version 1 architecture
2. Designing the Version 2 upgrade architecture
3. Then implementing modules step-by-step.

Write production-quality Python code and explain design decisions like a senior engineer mentoring a junior developer.