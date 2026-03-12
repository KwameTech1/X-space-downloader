You are a senior backend engineer and AI systems developer.

We already have Version 1 of a Twitter/X Spaces downloader built in Python.

The system currently includes:

- Space URL parser
- Twitter/X metadata fetcher
- HLS playlist parser
- async segment downloader
- audio merger using ffmpeg
- CLI interface

Example command:

space-downloader https://x.com/i/spaces/SPACE_ID

The downloader produces a final audio file such as:

space_ABC123.mp3

--------------------------------------------------

VERSION 1.2 OBJECTIVE

Upgrade the existing downloader so that after the audio is downloaded, the system can:

1. Convert the full Space audio into text (transcription)
2. Generate a clean readable transcript
3. Produce a structured summary for article writing

This feature should work automatically after the audio download completes.

IMPORTANT:
Do NOT redesign the downloader.

Extend the existing system by adding new modules.

--------------------------------------------------

FEATURE 1 — FULL AUDIO TRANSCRIPTION

The system must convert the entire Space audio into text.

Requirements:

• support long audio (1–4 hour Spaces)
• handle large audio files efficiently
• produce accurate transcripts
• preserve timestamps for segments

Recommended technology:

OpenAI Whisper or compatible speech-to-text models.

Output file:

space_ABC123_transcript.txt

The transcript should be formatted cleanly for reading and editing.

Example format:

[00:01:10]
Host: Welcome everyone to the Space today...

[00:02:15]
Speaker: Today we're discussing AI development in Africa...

--------------------------------------------------

FEATURE 2 — ARTICLE-READY TRANSCRIPT

After transcription, process the text into a cleaner article-ready format.

Tasks:

• remove filler words where possible
• clean sentence structure
• preserve speaker context
• maintain logical flow

Output:

space_ABC123_clean_transcript.txt

This file should be usable for blog writing or content creation.

--------------------------------------------------

FEATURE 3 — SPACE SUMMARY

Generate a structured summary from the transcript.

The summary should include:

• short overview (2–3 paragraphs)
• key topics discussed
• main insights
• notable quotes

Output file:

space_ABC123_summary.txt

Example structure:

TITLE:
Possible article headline

SUMMARY:
Short explanation of the discussion

KEY POINTS:
- Point 1
- Point 2
- Point 3

NOTABLE QUOTES:
"Quote from the discussion"

--------------------------------------------------

PROJECT STRUCTURE EXTENSION

Add new modules without breaking the existing downloader.

Example new structure:

transcription/
    transcriber.py
    transcript_cleaner.py

analysis/
    summarizer.py

--------------------------------------------------

WORKFLOW

The new pipeline should work like this:

1. user runs downloader command
2. audio file is downloaded
3. transcription begins automatically
4. transcript file is generated
5. transcript is cleaned
6. summary is generated

Final outputs:

audio file
transcript file
clean transcript
summary file

--------------------------------------------------

IMPLEMENTATION PLAN

Guide me step-by-step to implement this upgrade.

For each step include:

• command to run
• file to create
• code to write
• explanation

We will implement this in the terminal step-by-step.

--------------------------------------------------

IMPORTANT

Do not rewrite the downloader engine.

Extend it with new modules.

Write production-quality Python code and explain design decisions clearly.