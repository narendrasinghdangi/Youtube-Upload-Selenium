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
4. Run this script.

Usage
-----
    python main.py

        No platform flags passed -> full pipeline. Picks up the next
        unprocessed row(s) from content.csv, generates a thumbnail image
        + video for each, and uploads to every platform you're logged
        into.

    python main.py --yt true
    python main.py --yt true --insta false --fb false
    python main.py --yt true --video-id 3

        Passing any of --yt / --insta / --fb switches to selective mode:
        only the platform(s) explicitly set to true are uploaded to (any
        not mentioned are treated as false). A row_number (matching e.g.
        images/<row_number>.png and videos/<row_number>.mp4) is required —
        pass it with --video-id, or if omitted you'll be prompted for it.
        Image/video generation is skipped entirely and the existing files
        for that row are uploaded as-is.

The script connects to that Chrome, opens YouTube, Instagram and Facebook
each in their own tab, verifies you're logged in on each, then uploads.
"""

import argparse
import time
from dotenv import load_dotenv
from app.browser import BrowserSession
from app.model import Video
from app.log_utils import setup_logger
from app.data.read_data import read_data, read_row_by_id, update_row_status
from app.text_to_image import generate_image
from app.text_to_video import create_video_by_sora
from app.youtube_upload import upload_multiple_videos as youtube_upload
from app.insta_upload import upload_multiple_videos as insta_upload
from app.fb_upload import upload_multiple_videos as fb_upload

logger = setup_logger(__name__)

load_dotenv()

# --------------------------------------------------------------------------
# CLI args
# --------------------------------------------------------------------------

def _str2bool(value: str) -> bool:
    """Parses common truthy/falsy CLI strings ('true', '1', 'yes', ...) into bool."""
    normalized = value.strip().lower()
    if normalized in ("true", "1", "yes", "y", "t"):
        return True
    if normalized in ("false", "0", "no", "n", "f"):
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got: {value!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Upload videos to YouTube, Instagram and Facebook. Pass no "
            "platform flags to run the full pipeline (generate + upload "
            "everywhere you're logged in). Pass any of --yt/--insta/--fb "
            "to switch to selective mode: only the platform(s) explicitly "
            "set to true are uploaded to, you'll be prompted for a row "
            "number, and image/video generation is skipped (existing "
            "files for that row are reused)."
        )
    )
    parser.add_argument("--yt", type=_str2bool, default=None, help="Upload to YouTube (true/false).")
    parser.add_argument("--insta", type=_str2bool, default=None, help="Upload to Instagram (true/false).")
    parser.add_argument("--fb", type=_str2bool, default=None, help="Upload to Facebook (true/false).")
    parser.add_argument(
        "--video-id",
        type=int,
        default=None,
        help=(
            "Row number to upload in selective mode (matches "
            "images/<video_id>.png and videos/<video_id>.mp4). If omitted "
            "in selective mode, you'll be prompted for it."
        ),
    )
    return parser.parse_args()


# --------------------------------------------------------------------------
# Shared upload helper
# --------------------------------------------------------------------------

def _upload_to_platforms(
    session: BrowserSession,
    videos: list[Video],
    video_id: int,
    *,
    do_yt: bool,
    do_insta: bool,
    do_fb: bool,
) -> None:
    """Runs the upload for whichever platforms are enabled and records
    per-platform results back into content.csv."""
    driver = session.driver
    time.sleep(2)

    yt_status = yt_error = None
    insta_status = insta_error = None
    fb_status = fb_error = None

    if do_yt:
        logger.info("Starting YouTube uploads...")
        session.switch_to_youtube()
        yt_results = youtube_upload(driver, videos)
        success, error = yt_results[0]
        yt_status = "success" if success else "failed"
        yt_error = error
        logger.info("YouTube uploads complete.")
    else:
        logger.warning("Skipping YouTube.")

    time.sleep(30)
    if do_insta:
        logger.info("Starting Instagram uploads...")
        session.switch_to_instagram()
        insta_results = insta_upload(driver, videos)
        success, error = insta_results[0]
        insta_status = "success" if success else "failed"
        insta_error = error
        logger.info("Instagram uploads complete.")
    else:
        logger.warning("Skipping Instagram.")

    time.sleep(30)
    if do_fb:
        logger.info("Starting Facebook uploads...")
        session.switch_to_facebook()
        fb_results = fb_upload(driver, videos)
        success, error = fb_results[0]
        fb_status = "success" if success else "failed"
        fb_error = error
        logger.info("Facebook uploads complete.")
    else:
        logger.warning("Skipping Facebook.")

    update_row_status(
        video_id,
        yt_status=yt_status,
        yt_error=yt_error or "",
        insta_status=insta_status,
        insta_error=insta_error or "",
        fb_status=fb_status,
        fb_error=fb_error or "",
    )


# --------------------------------------------------------------------------
# Full pipeline (default): generate + upload everywhere
# --------------------------------------------------------------------------

def run_full_pipeline() -> None:
    logger.info("Connecting to Chrome...")
    session = BrowserSession()
    session.connect()

    logger.info("Setting up tabs (YouTube + Instagram + Facebook)...")
    session.setup_tabs()

    # Verify logins
    yt_ok, insta_ok, fb_ok = session.verify_logins()

    for i in range(2):
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

        _upload_to_platforms(
            session,
            videos,
            video_id,
            do_yt=yt_ok,
            do_insta=insta_ok,
            do_fb=fb_ok,
        )

        logger.warning(f"Done 1st loop")

    logger.info("All done! Chrome window left open for you.")


# --------------------------------------------------------------------------
# Selective mode: one or more of --yt/--insta/--fb passed
# --------------------------------------------------------------------------

def run_selective_upload(
    want_yt: bool, want_insta: bool, want_fb: bool, video_id: int | None = None
) -> None:
    """Skips image/video generation entirely, reuses existing files for
    the row number you specify, and uploads only to the requested
    platform(s)."""
    if not (want_yt or want_insta or want_fb):
        logger.error(
            "No platform set to true. Pass e.g. --yt true to upload to "
            "YouTube, or omit all platform flags to run the full pipeline."
        )
        return

    if video_id is None:
        row_input = input(
            "Enter row_number to upload (matches images/<row_number>.png and "
            "videos/<row_number>.mp4, e.g. 1): "
        ).strip()
        try:
            video_id = int(row_input)
        except ValueError:
            logger.error(f"Invalid row_number: {row_input!r}. Must be an integer.")
            return

    content = read_row_by_id(video_id)
    if content is None:
        logger.error(f"No row found for row_number {video_id} in content.csv.")
        return

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

    videos: list[Video] = [
        Video(
            video_title=video_title,
            video_description=video_description,
            thumbnail_file_path=thumbnail_file_path,
            video_file_path=video_file_path,
            tags=video_tags,
        )
    ]

    logger.info("Connecting to Chrome...")
    session = BrowserSession()
    session.connect()

    logger.info("Setting up tabs (YouTube + Instagram + Facebook)...")
    session.setup_tabs()

    yt_ok, insta_ok, fb_ok = session.verify_logins()

    _upload_to_platforms(
        session,
        videos,
        video_id,
        do_yt=want_yt and yt_ok,
        do_insta=want_insta and insta_ok,
        do_fb=want_fb and fb_ok,
    )

    logger.info("All done! Chrome window left open for you.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    args = parse_args()

    if args.yt is None and args.insta is None and args.fb is None:
        run_full_pipeline()
        return

    run_selective_upload(bool(args.yt), bool(args.insta), bool(args.fb), args.video_id)


if __name__ == "__main__":
    main()
