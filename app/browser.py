"""
browser.py

Shared Chrome browser session manager.

Instead of running separate Chrome instances per platform, this module
manages a SINGLE Chrome instance with remote debugging. YouTube, Instagram
and Facebook each get their own tab within that same browser window.

One-time setup
--------------
1. Close all Chrome windows.
2. Launch Chrome with remote debugging on a single profile:

   Windows (PowerShell):
     & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
         --remote-debugging-port=9222 `
         --user-data-dir="$env:USERPROFILE\\.upload_chrome_profile"

   macOS:
     open -na "Google Chrome" --args --remote-debugging-port=9222 \
         --user-data-dir="$HOME/.upload_chrome_profile"

   Linux:
     google-chrome --remote-debugging-port=9222 \
         --user-data-dir="$HOME/.upload_chrome_profile"

3. In that window, log into YouTube (youtube.com), Instagram
   (instagram.com) and Facebook (facebook.com) in separate tabs — just
   like you normally would.
4. Leave Chrome open. Run your script. It attaches to that browser and
   manages tabs for YouTube, Instagram and Facebook uploads.

Because all sites share the same browser profile, you only need ONE
Chrome instance and ONE login session per site.
"""

from __future__ import annotations

import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

try:
    from webdriver_manager.chrome import ChromeDriverManager
    _HAS_WDM = True
except ImportError:
    _HAS_WDM = False


DEBUGGER_ADDRESS = "127.0.0.1:9222"
YOUTUBE_URL = "https://www.youtube.com"
INSTAGRAM_URL = "https://www.instagram.com/"
FACEBOOK_URL = "https://www.facebook.com/"


class BrowserSession:
    """Manages a single Chrome session with separate tabs for YouTube, Instagram and Facebook."""

    def __init__(self):
        self.driver: webdriver.Chrome | None = None
        self.youtube_tab: str | None = None
        self.instagram_tab: str | None = None
        self.facebook_tab: str | None = None

    def connect(self) -> webdriver.Chrome:
        """Attach to the already-running Chrome with remote debugging."""
        options = Options()
        options.add_experimental_option("debuggerAddress", DEBUGGER_ADDRESS)

        if _HAS_WDM:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        else:
            self.driver = webdriver.Chrome(options=options)

        print(f"Connected to Chrome on {DEBUGGER_ADDRESS}")
        return self.driver

    def setup_tabs(self) -> None:
        """Opens YouTube, Instagram and Facebook each in their own tab.
        
        If tabs already have these sites open, reuses them instead of
        opening duplicates.
        """
        if self.driver is None:
            self.connect()

        driver = self.driver

        # Check existing tabs for YouTube / Instagram / Facebook
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            url = driver.current_url.lower()
            if "youtube.com" in url:
                self.youtube_tab = handle
            elif "instagram.com" in url:
                self.instagram_tab = handle
            elif "facebook.com" in url:
                self.facebook_tab = handle

        # Open YouTube tab if not found
        if self.youtube_tab is None:
            driver.switch_to.new_window("tab")
            self.youtube_tab = driver.current_window_handle
            driver.get(YOUTUBE_URL)
            time.sleep(2)

        # Open Instagram tab if not found
        if self.instagram_tab is None:
            driver.switch_to.new_window("tab")
            self.instagram_tab = driver.current_window_handle
            driver.get(INSTAGRAM_URL)
            time.sleep(2)

        # Open Facebook tab if not found
        if self.facebook_tab is None:
            driver.switch_to.new_window("tab")
            self.facebook_tab = driver.current_window_handle
            driver.get(FACEBOOK_URL)
            time.sleep(2)

        print(
            f"Tabs ready — YouTube: {self.youtube_tab}, "
            f"Instagram: {self.instagram_tab}, Facebook: {self.facebook_tab}"
        )

    def switch_to_youtube(self) -> None:
        """Switch focus to the YouTube tab."""
        if self.youtube_tab is None:
            raise RuntimeError("YouTube tab not set up. Call setup_tabs() first.")
        self.driver.switch_to.window(self.youtube_tab)

    def switch_to_instagram(self) -> None:
        """Switch focus to the Instagram tab."""
        if self.instagram_tab is None:
            raise RuntimeError("Instagram tab not set up. Call setup_tabs() first.")
        self.driver.switch_to.window(self.instagram_tab)

    def switch_to_facebook(self) -> None:
        """Switch focus to the Facebook tab."""
        if self.facebook_tab is None:
            raise RuntimeError("Facebook tab not set up. Call setup_tabs() first.")
        self.driver.switch_to.window(self.facebook_tab)

    def verify_youtube_login(self) -> bool:
        """Check that you're logged into YouTube."""
        self.switch_to_youtube()
        self.driver.get(YOUTUBE_URL)
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "avatar-btn"))
            )
            print("YouTube: logged in ✓")
            return True
        except TimeoutException:
            print("YouTube: NOT logged in — please log in manually in the Chrome window.")
            return False

    def verify_instagram_login(self) -> bool:
        """Check that you're logged into Instagram."""
        self.switch_to_instagram()
        self.driver.get(INSTAGRAM_URL)
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[@aria-label='New post' or @aria-label='Create']")
                )
            )
            print("Instagram: logged in ✓")
            return True
        except TimeoutException:
            print("Instagram: NOT logged in — please log in manually in the Chrome window.")
            return False

    def verify_facebook_login(self) -> bool:
        """Check that you're logged into Facebook."""
        self.switch_to_facebook()
        self.driver.get(FACEBOOK_URL)
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//*[@aria-label='Facebook menu' or @aria-label='Create' "
                        "or @aria-label='Create post' or @aria-label='Account']",
                    )
                )
            )
            print("Facebook: logged in ✓")
            return True
        except TimeoutException:
            print("Facebook: NOT logged in — please log in manually in the Chrome window.")
            return False

    def verify_logins(self) -> tuple[bool, bool, bool]:
        """Verify YouTube, Instagram and Facebook logins. Returns (yt_ok, insta_ok, fb_ok)."""
        yt = self.verify_youtube_login()
        insta = self.verify_instagram_login()
        fb = self.verify_facebook_login()
        return yt, insta, fb
