"""
main.py

Upload videos to YouTube, Instagram and Facebook from a single Chrome session.

Setup (one time per session):
1. Close all Chrome windows.
2. Launch Chrome with remote debugging:

   Windows (PowerShell):
     & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
         --remote-debugging-port=9222 `
         --user-data-dir="$env:USERPROFILE\\.upload_chrome_profile"

3. In that Chrome window, log into youtube.com, instagram.com and
   facebook.com (in any tabs you like).
4. Run this script:  python main.py

The script connects to that Chrome, opens YouTube, Instagram and Facebook
each in their own tab, verifies you're logged in on each, then uploads
your videos to all three platforms.
"""

import time
from dotenv import load_dotenv
from app.browser import BrowserSession
from app.model import Video
from app.log_utils import setup_logger
from app.data.read_data import read_data
from app.text_to_image import generate_image
from app.text_to_video import create_video_by_sora
from app.youtube_upload import upload_multiple_videos as youtube_upload
from app.insta_upload import upload_multiple_videos as insta_upload
from app.fb_upload import upload_multiple_videos as fb_upload

logger = setup_logger(__name__)

load_dotenv()

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    logger.info("Connecting to Chrome...")
    session = BrowserSession()
    session.connect()

    logger.info("Setting up tabs (YouTube + Instagram + Facebook)...")
    session.setup_tabs()

    # Verify logins
    yt_ok, insta_ok, fb_ok = session.verify_logins()

    content = read_data()
    if content is None:
        logger.error("No unprocessed rows found in content.csv. Nothing to do.")
        return

    video_id = content["id"]
    video_title = content["title"]
    video_description = content["description"]
    video_tags = content["hashtags"]
    thumbnail_file_path = f"images/{video_id}.png"
    video_file_path = f"videos/{video_id}.mp4"

    logger.warning(f"video_id: {video_id}, video_title: {video_title}")
    logger.warning(f"video_description: {video_description}")
    logger.warning(f"video_tags: {video_tags}")
    logger.warning(f"thumbnail_file_path: {thumbnail_file_path}")
    logger.warning(f"video_file_path: {video_file_path}")

    generate_image(thumbnail_file_path, video_title, video_description)
    create_video_by_sora(video_file_path, video_title, video_description)


    videos: list[Video] = [
        Video(
            video_title=video_title,
            video_description=video_description,
            thumbnail_file_path=thumbnail_file_path,
            video_file_path=video_file_path,
            tags=video_tags,
        )
    ]

    if not yt_ok and not insta_ok and not fb_ok:
        logger.error(
            "Not logged in on any platform. Please log in manually in "
            "the Chrome window and re-run this script."
        )
        return

    driver = session.driver
    time.sleep(2)

    # Upload to YouTube
    if yt_ok:
        logger.info("Starting YouTube uploads...")
        session.switch_to_youtube()
        youtube_upload(driver, videos)
        logger.info("YouTube uploads complete.")
    else:
        logger.warning("Skipping YouTube — not logged in.")

    time.sleep(30)
    # Upload to Instagram
    if insta_ok:
        logger.info("Starting Instagram uploads...")
        session.switch_to_instagram()
        insta_upload(driver, videos)
        logger.info("Instagram uploads complete.")
    else:
        logger.warning("Skipping Instagram — not logged in.")

    time.sleep(30)
    # Upload to Facebook
    if fb_ok:
        logger.info("Starting Facebook uploads...")
        session.switch_to_facebook()
        fb_upload(driver, videos)
        logger.info("Facebook uploads complete.")
    else:
        logger.warning("Skipping Facebook — not logged in.")

    logger.info("All done! Chrome window left open for you.")


if __name__ == "__main__":
    main()
