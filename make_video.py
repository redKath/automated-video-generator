"""topic -> vertical mp4: LLM script, stock/YouTube footage, edge-tts voice, burned captions, ducked music."""
import asyncio, json, os, re, subprocess, sys
from pathlib import Path

import edge_tts, requests
from dotenv import load_dotenv

load_dotenv()

VIDEO_WIDTH, VIDEO_HEIGHT, FRAMES_PER_SECOND = 1080, 1920, 30
FREE_LLM_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
]
TARGET_SECONDS, SCENE_COUNT = 45, 6
TTS_VOICE = "en-US-AndrewNeural"
BACKGROUND_MUSIC_PATH = Path(__file__).parent / "assets" / "music.mp3"
WORDS_PER_CAPTION = 4
CAPTION_STYLE = "FontName=Arial,Bold=1,FontSize=16,Outline=2,Alignment=2,MarginV=120"
PAUSE_AFTER_NARRATION_SECONDS = 0.3
MAX_FOOTAGE_SECONDS = 15
FALLBACK_CARD_COLOR = "0x1e2a44"


def write_scenes_with_llm(topic):
    """Returns [{"narration": str, "search_query": str}, ...]."""
    prompt = (
        f"Write a ~{TARGET_SECONDS} second narrated short video about: {topic}\n"
        'Return only JSON: {"scenes":[{"narration":"1-2 sentences","search_query":"2-3 word stock footage query"}]}. '
        f"{SCENE_COUNT} scenes, punchy hook first, concrete visual queries."
    )
    models = [os.environ["LLM_MODEL"]] if os.environ.get("LLM_MODEL") else FREE_LLM_MODELS
    for model in models:  # free models are often rate-limited, so try the next on failure
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=120,
        )
        if not response.ok:
            print(f"{model}: HTTP {response.status_code}, trying next")
            continue
        reply_text = response.json()["choices"][0]["message"]["content"]
        json_match = re.search(r"\{.*\}", reply_text, re.S)
        if json_match:
            return json.loads(json_match.group(0))["scenes"]
    raise RuntimeError("all LLM models failed; set LLM_MODEL or retry later")


async def synthesize_speech(narration, output_mp3_path):
    """Writes the mp3 and returns [(word, start_seconds, end_seconds), ...]."""
    word_timings = []
    communicate = edge_tts.Communicate(narration, TTS_VOICE, boundary="WordBoundary")
    with open(output_mp3_path, "wb") as mp3_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_seconds = chunk["offset"] / 1e7  # offsets are in 100ns ticks
                word_timings.append((chunk["text"], start_seconds, start_seconds + chunk["duration"] / 1e7))
    return word_timings


def download_pexels_clip(search_query, output_path):
    """Returns output_path, or None if no API key or no matching clip."""
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    response = requests.get(
        "https://api.pexels.com/videos/search",
        params={"query": search_query, "per_page": 5, "orientation": "portrait"},
        headers={"Authorization": api_key}, timeout=30,
    )
    candidate_files = [
        video_file
        for video in response.json().get("videos", [])
        for video_file in video["video_files"]
        if video_file["file_type"] == "video/mp4" and video_file["width"] >= 720
    ]
    if not candidate_files:
        return None
    smallest_hd_file = min(candidate_files, key=lambda video_file: video_file["width"])
    output_path.write_bytes(requests.get(smallest_hd_file["link"], timeout=120).content)
    return output_path


def download_youtube_clip(search_query, output_path):
    """Downloads the first MAX_FOOTAGE_SECONDS of the top search hit. Returns None on failure."""
    result = subprocess.run(
        [sys.executable, "-m", "yt_dlp", f"ytsearch1:{search_query} stock footage 4k", "--no-playlist",
         "-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]",
         "--download-sections", f"*0-{MAX_FOOTAGE_SECONDS}", "--force-keyframes-at-cuts",
         "--merge-output-format", "mp4", "-o", str(output_path), "-q"],
        capture_output=True, text=True,
    )
    return output_path if result.returncode == 0 and output_path.exists() else None


def run_ffmpeg(*args, working_dir=None):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True, cwd=working_dir)


def probe_duration_seconds(media_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout)


def format_srt_timestamp(total_seconds):
    hours, minutes = int(total_seconds // 3600), int(total_seconds % 3600 // 60)
    seconds, milliseconds = int(total_seconds % 60), int(total_seconds % 1 * 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def build_captions_srt(word_timings_per_scene, scene_start_offsets):
    srt_entries = []
    for word_timings, scene_start in zip(word_timings_per_scene, scene_start_offsets):
        for first in range(0, len(word_timings), WORDS_PER_CAPTION):
            caption_words = word_timings[first:first + WORDS_PER_CAPTION]
            start = format_srt_timestamp(scene_start + caption_words[0][1])
            end = format_srt_timestamp(scene_start + caption_words[-1][2])
            text = " ".join(word for word, _, _ in caption_words)
            srt_entries.append(f"{len(srt_entries) + 1}\n{start} --> {end}\n{text}\n")
    return "\n".join(srt_entries)


def render_scene_clip(footage_path, narration_mp3_path, scene_seconds, output_path):
    """Crops/loops footage to vertical video of scene_seconds with the narration as audio."""
    if footage_path:
        video_input = ["-stream_loop", "-1", "-i", footage_path]
    else:
        video_input = ["-f", "lavfi", "-i",
                       f"color=c={FALLBACK_CARD_COLOR}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={FRAMES_PER_SECOND}"]
    crop_to_vertical = (f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},fps={FRAMES_PER_SECOND},setsar=1")
    run_ffmpeg(*video_input, "-i", narration_mp3_path, "-t", scene_seconds,
               "-vf", crop_to_vertical, "-af", "apad",
               "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", output_path)


def mix_music_and_burn_captions(working_dir, total_seconds, output_path):
    """Reads joined.mp4 + captions.srt from working_dir; music is ducked under the narration."""
    if BACKGROUND_MUSIC_PATH.exists():
        music_input = ["-stream_loop", "-1", "-i", BACKGROUND_MUSIC_PATH.resolve()]
    else:
        music_input = ["-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100"]
    filter_graph = (
        "[0:a]asplit[narration_mix][narration_sidechain];"
        "[1:a]volume=0.25[music];"
        "[music][narration_sidechain]sidechaincompress=threshold=0.05:ratio=8[ducked_music];"
        "[narration_mix][ducked_music]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[audio];"
        f"[0:v]subtitles=captions.srt:force_style='{CAPTION_STYLE}'[video]"
    )
    run_ffmpeg("-i", "joined.mp4", *music_input, "-t", total_seconds, "-filter_complex", filter_graph,
               "-map", "[video]", "-map", "[audio]", "-c:v", "libx264", "-preset", "veryfast",
               "-pix_fmt", "yuv420p", "-c:a", "libmp3lame", "-b:a", "192k",  # mp3: some Windows players lack AAC
               "-shortest", output_path,
               working_dir=working_dir)  # relative srt path avoids Windows drive-colon escaping


def generate_video(topic):
    topic_slug = re.sub(r"\W+", "-", topic.lower()).strip("-")[:40]
    working_dir = Path("work") / topic_slug
    working_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path("out").resolve()
    output_dir.mkdir(exist_ok=True)
    final_video_path = output_dir / f"{topic_slug}.mp4"

    scenes = write_scenes_with_llm(topic)
    print(f"script: {len(scenes)} scenes")

    scene_clip_paths, word_timings_per_scene, scene_start_offsets = [], [], []
    elapsed_seconds = 0.0
    for scene_index, scene in enumerate(scenes):
        narration_path = working_dir / f"narration{scene_index}.mp3"
        footage_path = working_dir / f"footage{scene_index}.mp4"
        scene_clip_path = working_dir / f"scene{scene_index}.mp4"

        word_timings = asyncio.run(synthesize_speech(scene["narration"], narration_path))
        scene_seconds = probe_duration_seconds(narration_path) + PAUSE_AFTER_NARRATION_SECONDS

        footage_source = "pexels"
        footage = download_pexels_clip(scene["search_query"], footage_path)
        if not footage:
            footage_source = "yt-dlp"
            footage = download_youtube_clip(scene["search_query"], footage_path)
        print(f"scene {scene_index}: {scene_seconds:.1f}s '{scene['search_query']}' "
              f"-> {footage_source if footage else 'fallback card'}")

        render_scene_clip(footage, narration_path, scene_seconds, scene_clip_path)
        scene_clip_paths.append(scene_clip_path)
        word_timings_per_scene.append(word_timings)
        scene_start_offsets.append(elapsed_seconds)
        elapsed_seconds += probe_duration_seconds(scene_clip_path)

    (working_dir / "clip_list.txt").write_text("".join(f"file '{path.name}'\n" for path in scene_clip_paths))
    (working_dir / "captions.srt").write_text(
        build_captions_srt(word_timings_per_scene, scene_start_offsets), encoding="utf-8")
    run_ffmpeg("-f", "concat", "-safe", "0", "-i", "clip_list.txt", "-c", "copy", "joined.mp4",
               working_dir=working_dir)
    mix_music_and_burn_captions(working_dir, elapsed_seconds, final_video_path)
    print(f"done: {final_video_path} ({elapsed_seconds:.1f}s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: python make_video.py "topic"')
    generate_video(" ".join(sys.argv[1:]))
