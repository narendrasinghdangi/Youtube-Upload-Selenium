"""
youtube_upload.py

Selenium-based automation for uploading videos to YouTube Studio.

This module now works with a shared BrowserSession (from app.browser) so that
YouTube and Instagram uploads happen in the SAME Chrome window, just in
different tabs. You no longer need a separate Chrome instance for YouTube.

See app/browser.py for the one-time Chrome setup instructions.
"""

from __future__ import annotations

import os
import time

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .model import Video

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

UPLOAD_URL = "https://www.youtube.com/upload"
DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 300  # video file processing can take a while


# --------------------------------------------------------------------------
# Upload flow helpers
# --------------------------------------------------------------------------

def _wait(driver, timeout=DEFAULT_TIMEOUT):
    return WebDriverWait(driver, timeout)


def _click(driver, by, selector, timeout=DEFAULT_TIMEOUT):
    el = _wait(driver, timeout).until(EC.element_to_be_clickable((by, selector)))
    try:
        el.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", el)
    return el


def _set_textbox(el, text: str):
    """Clears a YouTube Studio contenteditable textbox and types new text."""
    el.click()
    el.send_keys(Keys.CONTROL, "a")
    el.send_keys(Keys.BACKSPACE)
    el.send_keys(text)


def _select_file(driver, input_selector: str, file_path: str):
    file_input = driver.find_element(By.CSS_SELECTOR, input_selector)
    file_input.send_keys(os.path.abspath(file_path))


def upload_video(driver: webdriver.Chrome, video: Video) -> None:
    """Uploads a single Video through YouTube Studio's upload dialog.
    
    The driver should already be focused on the YouTube tab (call
    browser_session.switch_to_youtube() before calling this).
    """
    print(f"[YouTube] Uploading: {video.video_title}")

    driver.get(UPLOAD_URL)

    # --- Step 1: select the video file --------------------------------
    _select_file(driver, "input[type='file']", video.video_file_path)

    # Wait for the upload dialog / details step to appear.
    _wait(driver, LONG_TIMEOUT).until(
        EC.presence_of_element_located((By.ID, "textbox"))
    )
    time.sleep(2)

    # --- Step 2: title ---------------------------------------------------
    title_box = driver.find_elements(By.ID, "textbox")[0]
    _set_textbox(title_box, video.video_title)

    # --- Step 3: description ---------------------------------------------
    desc_box = driver.find_elements(By.ID, "textbox")[1]
    _set_textbox(desc_box, video.video_description)

    # --- Step 4: thumbnail ------------------------------------------------
    if video.thumbnail_file_path:
        try:
            thumb_input = driver.find_element(
                By.CSS_SELECTOR, "input#file-loader"
            )
            thumb_input.send_keys(os.path.abspath(video.thumbnail_file_path))
            time.sleep(1)
        except NoSuchElementException:
            print("  (thumbnail upload control not found, skipping)")

    # --- Step 4b: "Made for kids" (required) — select "No, it's not made for kids"
    def _select_not_for_kids() -> bool:
        try:
            radio = _wait(driver).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']")
                )
            )
        except TimeoutException:
            return False

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", radio
        )
        for attempt in range(3):
            if attempt == 0:
                try:
                    radio.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", radio)
            else:
                driver.execute_script("arguments[0].click();", radio)
            time.sleep(0.5)
            if radio.get_attribute("aria-checked") == "true":
                return True
        return False

    if not _select_not_for_kids():
        print(
            "  WARNING: could not confirm 'Made for kids' was set to "
            "'not made for kids' — check this manually."
        )

    # --- Step 5: "Show more" -> tags, language, AI disclosure, etc. ---------
    try:
        _click(driver, By.XPATH, "//*[contains(text(),'Show more')]")
        time.sleep(1)
    except TimeoutException:
        pass

    # AI disclosure: "Was AI used to generate or edit your content?"
    # Select "Yes" to add an AI disclosure label to the video.
    if video.ai_generated:
        try:
            ai_yes_radio = _wait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "tp-yt-paper-radio-button[name='VIDEO_HAS_ALTERED_CONTENT_YES']")
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", ai_yes_radio
            )
            time.sleep(0.5)
            for attempt in range(3):
                if attempt == 0:
                    try:
                        ai_yes_radio.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", ai_yes_radio)
                else:
                    driver.execute_script("arguments[0].click();", ai_yes_radio)
                time.sleep(0.5)
                if ai_yes_radio.get_attribute("aria-checked") == "true":
                    print("  AI disclosure set to 'Yes'.")
                    break
            else:
                print("  WARNING: could not confirm AI disclosure was set to 'Yes'.")
        except TimeoutException:
            print("  (AI disclosure option not found, skipping)")

    # Tags
    if video.tags:
        try:
            _wait(driver).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "ytcp-form-input-container input")
                )
            )
            tags_input = driver.find_element(
                By.CSS_SELECTOR, "input.tag-input, input[aria-label='Tags']"
            )
            for tag in video.tags:
                tags_input.send_keys(tag)
                tags_input.send_keys(",")
            time.sleep(0.5)
        except (NoSuchElementException, TimeoutException):
            print("  (tags field not found, skipping tags)")

    # Category (e.g. "Comedy") — this is a custom dropdown, not a native
    # <select>. Click the "#category" dropdown trigger to open the popup
    # list, then click the option matching video.category.
    if video.category:
        try:
            category_trigger = _wait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "#category #trigger, ytcp-form-select#category ytcp-dropdown-trigger")
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", category_trigger
            )
            try:
                category_trigger.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", category_trigger)
            time.sleep(1)

            option = _wait(driver, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        f"//tp-yt-paper-listbox//*[normalize-space(text())='{video.category}']"
                        f"/ancestor::tp-yt-paper-item[1]"
                        f" | //tp-yt-paper-listbox//tp-yt-paper-item[normalize-space(text())='{video.category}']",
                    )
                )
            )
            try:
                option.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", option)
            time.sleep(0.5)
            print(f"  Category set to '{video.category}'.")
        except TimeoutException:
            print(f"  WARNING: could not set category to '{video.category}' — skipping.")

    # Move to next steps: Details -> Video elements -> Checks -> Visibility
    for _ in range(3):
        try:
            _click(driver, By.ID, "next-button")
            time.sleep(1.5)
        except TimeoutException:
            break

    # Set visibility to PUBLIC
    _click(driver, By.XPATH, "//tp-yt-paper-radio-button[@name='PUBLIC']")

    # --- Step 7: wait for processing to finish enough to publish ------------
    try:
        _wait(driver, LONG_TIMEOUT).until(
            lambda d: "Uploading" not in d.find_element(
                By.CSS_SELECTOR, ".progress-label"
            ).text
        )
    except (TimeoutException, NoSuchElementException):
        pass

    # --- Step 8: publish ---------------------------------------------------
    publish_selector = (
        By.XPATH,
        "//button[@aria-label='Publish' or @aria-label='Schedule' or @aria-label='Save']",
    )
    try:
        _click(driver, *publish_selector)
    except TimeoutException:
        print("  Could not find the final Publish/Schedule/Save button.")
        return

    time.sleep(10)

    # Handle "We're still checking your content" dialog
    try:
        _click(
            driver,
            By.XPATH,
            "//button[@aria-label='Publish anyway' or contains(., 'Publish anyway')]",
            timeout=5,
        )
        time.sleep(3)
    except TimeoutException:
        pass

    # Retry publish if still visible
    try:
        _click(driver, *publish_selector, timeout=5)
        time.sleep(3)
    except TimeoutException:
        pass

    # Close dialog
    time.sleep(3)
    try:
        _click(driver, By.CSS_SELECTOR, "#close-icon-button, ytcp-button#close-button", timeout=5)
    except TimeoutException:
        pass

    print(f"  [YouTube] Done: {video.video_title}")


def upload_multiple_videos(driver: webdriver.Chrome, videos: list[Video]) -> None:
    """Uploads each video to YouTube using the provided driver.
    
    The driver should already be on the YouTube tab. Call
    browser_session.switch_to_youtube() before calling this.
    """
    for video in videos:
        try:
            upload_video(driver, video)
        except Exception as exc:  # noqa: BLE001
            print(f"[YouTube] Failed to upload '{video.video_title}': {type(exc).__name__}: {exc!r}")
        time.sleep(2)
