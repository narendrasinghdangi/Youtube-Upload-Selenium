import os
import time
from openai import OpenAI
from dotenv import load_dotenv
from google import genai
from .model import video_system_prompt
from .log_utils import setup_logger

logger = setup_logger(__name__)

load_dotenv()  # take environment variables from .env.

openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def create_video_by_sora(video_file_path, video_title, video_description):
    logger.info("Starting video generation...")

    video_prompt = video_system_prompt.format(video_title=video_title, video_description=video_description)
    logger.info(f"Video prompt: {video_prompt}")
    video = openai.videos.create(
        model="sora-2",
        prompt=video_prompt,
        seconds="8",
        size="720x1280"
    )

    logger.info(f"Video generation started: {video}")

    progress = getattr(video, "progress", 0)
    bar_length = 30

    while video.status in ("in_progress", "queued"):
        # Refresh status
        video = openai.videos.retrieve(video.id)
        progress = getattr(video, "progress", 0)

        filled_length = int((progress / 100) * bar_length)
        bar = "=" * filled_length + "-" * (bar_length - filled_length)
        status_text = "Queued" if video.status == "queued" else "Processing"
        logger.info(f"{status_text}: [{bar}] {progress:.1f}%")
        time.sleep(5)

    if video.status == "failed":
        message = getattr(
            getattr(video, "error", None), "message", "Video generation failed"
        )
        logger.error(message)
        return

    logger.info(f"Video generation completed: {video}")
    logger.info("Downloading video content...")

    content = openai.videos.download_content(video.id, variant="video")
    content.write_to_file(video_file_path)
    logger.info(f"Wrote {video_file_path}")

def gemini_create_video():
    prompt = """A close up of two people staring at a cryptic drawing on a wall, torchlight flickering.
    A man murmurs, 'This must be it. That's the secret code.' The woman looks at him and whispering excitedly, 'What did you find?'"""

    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=prompt,
    )

    # Poll the operation status until the video is ready.
    while not operation.done:
        logger.info("Waiting for video generation to complete...")
        time.sleep(10)
        operation = client.operations.get(operation)

    # Download the generated video.
    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)
    logger.info("Downloading video content...")
    generated_video.video.save(video_file_path)
    logger.info("Generated video saved to dialogue_example.mp4")

if __name__ == "__main__":
    gemini_create_video()