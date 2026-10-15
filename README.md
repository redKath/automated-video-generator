# automated-video-gen

Topic -> 1080x1920 mp4 (script, stock footage, voiceover, captions, music).

1. `pip install -r requirements.txt` (ffmpeg on PATH)
2. Set `OPENROUTER_API_KEY` (openrouter.ai/keys; optional `LLM_MODEL`) and `PEXELS_API_KEY` (free: pexels.com/api)
3. Optional: drop `assets/music.mp3` (otherwise a quiet synth tone is used)
4. `python make_video.py "how black holes form"` -> `out/<topic>.mp4`

Without `PEXELS_API_KEY`, scenes fall back to solid color cards.
