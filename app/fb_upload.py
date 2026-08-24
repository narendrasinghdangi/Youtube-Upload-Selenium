"""
fb_upload.py

Selenium-based automation for uploading Reels to Facebook via the web UI
(facebook.com).

This module works with a shared BrowserSession (from app.browser) so that
YouTube, Instagram and Facebook uploads happen in the SAME Chrome window,
just in different tabs. You don't need a separate Chrome instance for
Facebook.

See app/browser.py for the one-time Chrome setup instructions.

Upload flow
-----------
1. Click "Create" -> select "Reel".
2. Upload the video file.
3. Set "Add AI label" toggle to True/Yes (required for AI-made/edited
   realistic content per Facebook's policy).
4. Add caption/details.
5. Click "Post" to publish.
"""

from __future__ import annotations

import os
import time
import traceback

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
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

HOME_URL = "https://www.facebook.com/"
DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 300  # video processing / transcoding can take a while


# --------------------------------------------------------------------------
# Upload flow helpers
# --------------------------------------------------------------------------

def _wait(driver, timeout=DEFAULT_TIMEOUT):
    return WebDriverWait(driver, timeout)


def _click(driver, by, selector, timeout=DEFAULT_TIMEOUT):
    el = _wait(driver, timeout).until(EC.element_to_be_clickable((by, selector)))
    _robust_click(driver, el)
    return el


def _robust_click(driver, el) -> None:
    """Try several click strategies in order, falling back progressively.

    Facebook's menu rows (e.g. the "Reel" row in the Create dropdown) are
    plain divs with `role="button"` whose last child is an absolutely
    positioned `role="none"` overlay (used for the hover highlight) sitting
    on top of the row at the exact point Selenium's native click would
    land. That overlay intercepts the native click, and some rows attach
    their handlers to pointer/mouse events rather than a plain `click`, so
    a bare `el.click()` or `element.click()` via JS isn't always enough.
    """
    try:
        el.click()
        return
    except (ElementClickInterceptedException, ElementNotInteractableException):
        pass

    try:
        driver.execute_script("arguments[0].click();", el)
        return
    except Exception:  # noqa: BLE001
        pass

    # Last resort: synthesize the full pointer/mouse event sequence at the
    # element's own center, bypassing hit-testing entirely.
    driver.execute_script(
        """
        const el = arguments[0];
        el.scrollIntoView({block: 'center'});
        const rect = el.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        const opts = {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y};
        for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
            el.dispatchEvent(new MouseEvent(type, opts));
        }
        """,
        el,
    )


_IN_VIEWPORT_JS = """
const el = arguments[0];
const r = el.getBoundingClientRect();
const vw = window.innerWidth || document.documentElement.clientWidth;
const vh = window.innerHeight || document.documentElement.clientHeight;
return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
"""


def _find_visible(driver, by, selector, timeout=DEFAULT_TIMEOUT):
    """Like presence_of_element_located, but skips over matches that exist
    in the DOM but aren't visible/interactable.

    This checks both `is_displayed()` AND that the element's bounding box
    actually falls inside the viewport. Facebook keeps off-screen clones of
    popup menus in the DOM (e.g. translated via a negative `top` offset,
    used for measuring/positioning before the real menu is shown) which
    pass `is_displayed()` but aren't the one the user can actually see or
    click. Without the viewport check we could grab the wrong clone and
    click/type into the wrong element.
    """

    def _first_visible(drv):
        for el in drv.find_elements(by, selector):
            try:
                if el.is_displayed() and drv.execute_script(_IN_VIEWPORT_JS, el):
                    return el
            except Exception:  # noqa: BLE001
                continue
        return False

    return _wait(driver, timeout).until(_first_visible)


def _type_into_contenteditable(driver, el, text: str):
    """Clears a Facebook contenteditable caption box and types new text."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        el.click()
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.BACKSPACE)
        if text:
            el.send_keys(text)
        return
    except ElementNotInteractableException:
        pass

    # Fallback: use JS to focus + dispatch input events so React picks up
    # the change, in case the element still isn't natively clickable.
    driver.execute_script("arguments[0].focus();", el)
    driver.execute_script("document.execCommand('selectAll', false, null);")
    driver.execute_script("document.execCommand('delete', false, null);")
    if text:
        driver.execute_script("document.execCommand('insertText', false, arguments[0]);", text)


def _select_file(driver, file_path: str):
    """Facebook's file input is typically `display:none` (unlike
    Instagram's, which is just off-screen), so send_keys raises
    ElementNotInteractableException unless we force it visible first."""
    file_input = _wait(driver).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
    )
    driver.execute_script(
        "arguments[0].style.display='block';"
        "arguments[0].style.visibility='visible';"
        "arguments[0].style.opacity='1';"
        "arguments[0].style.height='1px';"
        "arguments[0].style.width='1px';",
        file_input,
    )
    file_input.send_keys(os.path.abspath(file_path))


def _fill_tags(driver, tags: list[str]) -> None:
    """Best-effort: adds tags on the Reel details screen, before clicking
    Next. Facebook's tag field is a plain search input
    (`aria-label="Add tags"`, `type="search"`) whose placeholder hint says
    "Enter tags separated by a comma or semicolon" — it's comma-delimited
    free text, not a chip/token field that needs Enter after each tag.
    """
    if not tags:
        return

    try:
        tag_input = _find_visible(
            driver,
            By.XPATH,
            "//input[@aria-label='Add tags'] "
            "| //input[contains(@aria-label,'tag') or contains(@aria-label,'Tag') "
            "or contains(@aria-label,'topic') or contains(@aria-label,'Topic')]"
            " | //*[@contenteditable='true'][contains(@aria-label,'tag') "
            "or contains(@aria-label,'Tag')]",
            timeout=8,
        )
    except TimeoutException:
        print("  (tags field not found, skipping tags)")
        return

    try:
        tag_input.click()
        tag_input.send_keys(", ".join(tags))
        time.sleep(0.5)
        print(f"  Tags added: {', '.join(tags)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: could not add tags: {type(exc).__name__}: {exc!r}")


def _toggle_ai_label(driver, enable: bool) -> None:
    """Enable the 'Add AI label' toggle on the Reel details screen.

    The toggle is an <input role="switch" type="checkbox" aria-label="Add AI
    label" aria-checked="false">, next to the text "Add AI label" and the
    description "We require you to label certain realistic content that's
    made with AI."
    """
    if not enable:
        return

    try:
        switch = _wait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[role='switch'][aria-label='Add AI label']")
            )
        )
    except TimeoutException:
        # Fallback: any switch near the "Add AI label" text
        try:
            switch = _wait(driver, 5).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//*[contains(text(),'Add AI label')]"
                        "/ancestor::div[1]/following::input[@role='switch'][1]"
                        " | //*[contains(text(),'Add AI label')]/ancestor::div[3]//input[@role='switch']",
                    )
                )
            )
        except TimeoutException:
            print("  WARNING: could not find the 'Add AI label' toggle — skipping.")
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
    """Uploads a single Video as a Reel through Facebook's web create dialog.

    The driver should already be focused on the Facebook tab (call
    browser_session.switch_to_facebook() before calling this).
    """
    print(f"[Facebook] Uploading: {video.video_file_path}")

    driver.get(HOME_URL)
    time.sleep(2)

    # --- Step 1: open the "Facebook menu" (grid/"+" icon) -> Create dropdown
    # NOTE: deliberately NOT matching aria-label="Create post" here — that
    # label belongs to the "What's on your mind" quick-post composer, which
    # opens a plain Post dialog directly and skips the Reel/Story/Post
    # dropdown entirely. Only the menu that leads to a "Reel" choice should
    # be opened.
    try:
        _click(
            driver,
            By.XPATH,
            "//*[@aria-label='Facebook menu' or @aria-label='Create']",
            timeout=10,
        )
    except TimeoutException:
        print("  Could not find the Facebook/Create menu button.")
        return
    time.sleep(1.5)

    # --- Step 2: select "Reel" from the menu ------------------------------
    # Facebook's "Create" dropdown lists options in this order: Post,
    # Story, Reel, Life update. Matching on text alone risks grabbing the
    # wrong row if a stray/off-screen clone of the menu is in the DOM (see
    # _find_visible), so we scope the XPath to the actual clickable
    # row (role="button"/"link") that CONTAINS a "Reel" label, and click
    # that row directly rather than the inner span.
    try:
        reel_option = _find_visible(
            driver,
            By.XPATH,
            "//*[@role='button' or @role='link']"
            "[.//span[normalize-space(text())='Reel']]",
            timeout=10,
        )
        _robust_click(driver, reel_option)
    except TimeoutException:
        print("  Could not find the 'Reel' option in the menu.")
        return
    time.sleep(2)

    # --- Step 3: select the video file -----------------------------------
    try:
        _select_file(driver, video.video_file_path)
    except TimeoutException:
        print("  Could not find the file upload input.")
        return

    # Wait for the Reel editor / details step to render, confirming the
    # file was accepted.
    _wait(driver, LONG_TIMEOUT).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'Next') or contains(text(),'Post')]")
        )
    )
    time.sleep(2)

    # --- Step 4: add tags, then click through "Next" screens -------------
    _fill_tags(driver, video.tags)

    for _ in range(3):
        try:
            next_btn = _find_visible(
                driver,
                By.XPATH,
                "//div[@aria-label='Next'] "
                "| //*[@role='button' or @role='link'][.//span[normalize-space(text())='Next']]",
                timeout=5,
            )
        except TimeoutException:
            break
        _robust_click(driver, next_btn)
        time.sleep(1.5)

    # --- Step 5: caption/description --------------------------------------
    caption = video.build_caption()
    try:
        caption_box = _find_visible(
            driver,
            By.XPATH,
            "//div[@aria-label='Describe your Reel...'] "
            "| //div[@aria-label='Write a description...'] "
            "| //div[@contenteditable='true'][@role='textbox']",
            timeout=LONG_TIMEOUT,
        )
        _type_into_contenteditable(driver, caption_box, caption)
    except TimeoutException:
        print("  WARNING: could not find the caption box — skipping caption.")

    # --- Step 6: AI label toggle -------------------------------------------
    _toggle_ai_label(driver, video.ai_generated)

    # --- Step 7: publish ("Post") -------------------------------------------
    try:
        post_btn = _find_visible(
            driver,
            By.XPATH,
            "//div[@aria-label='Post'] "
            "| //*[@role='button' or @role='link'][.//span[normalize-space(text())='Post']]",
            timeout=DEFAULT_TIMEOUT,
        )
    except TimeoutException:
        print("  Could not find the Post button.")
        return
    _robust_click(driver, post_btn)

    # --- Step 8: wait for the upload/processing to complete -------------------
    try:
        _wait(driver, LONG_TIMEOUT).until(
            EC.invisibility_of_element_located(
                (By.XPATH, "//div[@aria-label='Post']")
            )
        )
    except TimeoutException:
        print("  WARNING: did not confirm the Post dialog closed — check manually.")

    print(f"  [Facebook] Done: {video.video_file_path}")


def upload_multiple_videos(driver: webdriver.Chrome, videos: list[Video]) -> None:
    """Uploads each video to Facebook (as a Reel) using the provided driver.

    The driver should already be on the Facebook tab. Call
    browser_session.switch_to_facebook() before calling this.
    """
    for video in videos:
        try:
            upload_video(driver, video)
        except Exception as exc:  # noqa: BLE001
            print(f"[Facebook] Failed to upload '{video.video_file_path}': {type(exc).__name__}: {exc!r}")
            traceback.print_exc()
        time.sleep(2)
