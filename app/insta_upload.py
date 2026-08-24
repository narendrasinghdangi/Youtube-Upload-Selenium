"""
insta_upload.py

Selenium-based automation for uploading Reels/videos to Instagram via the
web UI (instagram.com).

This module now works with a shared BrowserSession (from app.browser) so that
YouTube and Instagram uploads happen in the SAME Chrome window, just in
different tabs. You no longer need a separate Chrome instance for Instagram.

See app/browser.py for the one-time Chrome setup instructions.
"""

from __future__ import annotations

import os
import time

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
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

HOME_URL = "https://www.instagram.com/"
DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 300  # video processing / transcoding can take a while


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


def _type_into_contenteditable(el, text: str):
    """Clears an Instagram contenteditable caption box and types new text."""
    el.click()
    el.send_keys(Keys.CONTROL, "a")
    el.send_keys(Keys.BACKSPACE)
    if text:
        el.send_keys(text)


def _select_file(driver, file_path: str):
    """Instagram's file input is usually hidden off-screen rather than
    display:none, so send_keys works directly on it."""
    file_input = _wait(driver).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
    )
    file_input.send_keys(os.path.abspath(file_path))


def _toggle_ai_generated_content(driver, enable: bool) -> None:
    """Enable the 'Add AI label' toggle on the caption/share screen.
    
    The toggle is an <input role="switch" type="checkbox" aria-checked="false">
    next to the "Add AI label" text.
    """
    if not enable:
        return

    # The AI label switch is an input[role="switch"][type="checkbox"]
    # It's visible on the share/caption screen directly (no "Advanced settings" expand needed
    # in newer flows), but try expanding if present.
    try:
        _click(driver, By.XPATH, "//*[contains(text(),'Advanced settings') or contains(text(),'More options')]", timeout=3)
        time.sleep(0.5)
    except TimeoutException:
        pass

    # Find the switch input — it's near the "Add AI label" text
    try:
        switch = _wait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@role='switch'][@type='checkbox']")
            )
        )
    except TimeoutException:
        print("  WARNING: could not find the AI label toggle — skipping.")
        return

    is_checked = switch.get_attribute("aria-checked") == "true"
    if not is_checked:
        try:
            switch.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", switch)
        time.sleep(0.5)
        print("  AI label enabled.")
    else:
        print("  AI label already enabled.")


# --------------------------------------------------------------------------
# Main per-video upload
# --------------------------------------------------------------------------

def upload_video(driver: webdriver.Chrome, video: Video) -> None:
    """Uploads a single Video through Instagram's web create-post dialog.
    
    The driver should already be focused on the Instagram tab (call
    browser_session.switch_to_instagram() before calling this).
    """
    print(f"[Instagram] Uploading: {video.video_file_path}")

    driver.get(HOME_URL)

    # --- Step 1: open the "Create" dialog -------------------------------
    _click(
        driver,
        By.XPATH,
        "//*[@aria-label='New post' or @aria-label='Create']"
        "/ancestor::*[self::a or @role='button'][1]",
    )
    time.sleep(2)  # wait for the create menu to appear

    # After clicking Create, Instagram shows a menu: Post, Reel, Story, etc.
    # Click "Post" to open the file upload dialog.
    time.sleep(1)
    try:
        _click(
            driver,
            By.XPATH,
            "//*[text()='Post' or contains(text(),'Post')]"
            "[ancestor::*[@role='menu' or @role='dialog' or @role='list'] "
            "or ancestor::div[contains(@class,'x')]]",
            timeout=10,
        )
    except TimeoutException:
        # Fallback: try a broader match for the "Post" option
        try:
            _click(driver, By.XPATH, "//span[text()='Post'] | //div[text()='Post'] | //*[@role='menuitem'][.//text()='Post']", timeout=5)
        except TimeoutException:
            pass  # Some flows go directly to file picker without this menu
    time.sleep(1)

    # --- Step 2: select the video file -----------------------------------
    _select_file(driver, video.video_file_path)

    # Wait for the crop/edit step
    _wait(driver, LONG_TIMEOUT).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'Crop') or contains(text(),'Next')]")
        )
    )
    time.sleep(2)

    # --- Step 3: click through "Next" screens ----------------------------
    for _ in range(4):
        try:
            _click(driver, By.XPATH, "//div[text()='Next']", timeout=5)
            time.sleep(1.5)
        except TimeoutException:
            break

    # --- Step 4: caption -----------------------------------------------------
    caption = video.build_caption()
    try:
        caption_box = _wait(driver, LONG_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[aria-label='Write a caption...']")
            )
        )
        _type_into_contenteditable(caption_box, caption)
    except TimeoutException:
        print("  WARNING: could not find the caption box — skipping caption.")

    # --- Step 5: AI-generated content toggle ---------------------------------
    _toggle_ai_generated_content(driver, video.ai_generated)

    # --- Step 6: publish ("Share") -------------------------------------------
    try:
        _click(driver, By.XPATH, "//div[text()='Share']", timeout=DEFAULT_TIMEOUT)
    except TimeoutException:
        print("  Could not find the Share button.")
        return

    # --- Step 7: wait for the upload to complete -------------------
    try:
        _wait(driver, LONG_TIMEOUT).until(
            EC.invisibility_of_element_located(
                (By.XPATH, "//div[text()='Share']")
            )
        )
    except TimeoutException:
        print("  WARNING: did not confirm the Share dialog closed — check manually.")

    # Close any leftover confirmation dialog
    try:
        _click(
            driver,
            By.XPATH,
            "//button[@aria-label='Close' or contains(., 'Close')]",
            timeout=5,
        )
    except TimeoutException:
        pass

    print(f"  [Instagram] Done: {video.video_file_path}")


def upload_multiple_videos(driver: webdriver.Chrome, videos: list[Video]) -> None:
    """Uploads each video to Instagram using the provided driver.
    
    The driver should already be on the Instagram tab. Call
    browser_session.switch_to_instagram() before calling this.
    """
    for video in videos:
        try:
            upload_video(driver, video)
        except Exception as exc:  # noqa: BLE001
            print(f"[Instagram] Failed to upload '{video.video_file_path}': {type(exc).__name__}: {exc!r}")
        time.sleep(2)
