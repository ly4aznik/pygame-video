import argparse
import getpass
import os
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


INSTAGRAM_HOME_URL = "https://www.instagram.com/"
INSTAGRAM_LOGIN_URL = "https://www.instagram.com/accounts/login/"


class InstagramUploadError(RuntimeError):
    pass


def wait(driver: WebDriver, seconds: int = 30) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def first_present(driver: WebDriver, selectors: list[tuple[str, str]], seconds: int = 30):
    end_time = time.time() + seconds
    last_error: Exception | None = None

    while time.time() < end_time:
        for by, value in selectors:
            try:
                return WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((by, value))
                )
            except TimeoutException as exc:
                last_error = exc
        time.sleep(0.25)

    raise TimeoutException(f"None of the selectors appeared: {selectors}") from last_error


def first_clickable(driver: WebDriver, selectors: list[tuple[str, str]], seconds: int = 30):
    end_time = time.time() + seconds
    last_error: Exception | None = None

    while time.time() < end_time:
        for by, value in selectors:
            try:
                return WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((by, value))
                )
            except TimeoutException as exc:
                last_error = exc
        time.sleep(0.25)

    raise TimeoutException(f"None of the selectors became clickable: {selectors}") from last_error


def click_first(driver: WebDriver, selectors: list[tuple[str, str]], seconds: int = 30) -> None:
    element = first_clickable(driver, selectors, seconds)
    driver.execute_script("arguments[0].click();", element)


def create_driver(profile_dir: Path | None, headless: bool) -> WebDriver:
    options = ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--remote-debugging-port=0")

    if profile_dir:
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")

    if headless:
        options.add_argument("--headless=new")

    try:
        return webdriver.Chrome(options=options)
    except SessionNotCreatedException as exc:
        profile_hint = f"\nChrome profile dir: {profile_dir}" if profile_dir else ""
        raise InstagramUploadError(
            "Chrome failed to start. Close all Chrome/ChromeDriver windows started by "
            "this uploader, or rerun with a different --profile-dir."
            f"{profile_hint}"
        ) from exc


def is_logged_in(driver: WebDriver) -> bool:
    driver.get(INSTAGRAM_HOME_URL)
    try:
        first_present(
            driver,
            [
                (By.XPATH, "//*[@aria-label='New post' or @aria-label='Create']"),
                (By.XPATH, "//*[text()='Create']"),
                (By.CSS_SELECTOR, "svg[aria-label='New post']"),
                (By.CSS_SELECTOR, "svg[aria-label='Home']"),
            ],
            seconds=10,
        )
        return True
    except TimeoutException:
        return False


def wait_for_manual_login(driver: WebDriver) -> None:
    print("Log in to Instagram in the opened Chrome window.")
    input("After the Instagram home page loads, press Enter here to continue...")

    if not is_logged_in(driver):
        raise InstagramUploadError("Instagram login was not detected after manual login.")


def login(driver: WebDriver, username: str, password: str) -> None:
    driver.get(INSTAGRAM_LOGIN_URL)

    username_input = first_present(driver, [(By.NAME, "username")], seconds=30)
    password_input = first_present(driver, [(By.NAME, "password")], seconds=30)

    username_input.clear()
    username_input.send_keys(username)
    password_input.clear()
    password_input.send_keys(password)
    password_input.send_keys(Keys.ENTER)

    print("Logged in form submitted. Waiting for Instagram home page...")
    try:
        wait(driver, 45).until(lambda d: d.current_url != INSTAGRAM_LOGIN_URL)
    except TimeoutException:
        pass

    if not is_logged_in(driver):
        input(
            "Instagram may be waiting for 2FA, captcha, or account confirmation. "
            "Finish it in the browser, then press Enter here..."
        )

    if not is_logged_in(driver):
        raise InstagramUploadError("Login was not completed.")


def dismiss_optional_dialogs(driver: WebDriver) -> None:
    optional_buttons = [
        "Not now",
        "Not Now",
        "Skip",
        "Cancel",
    ]

    for text in optional_buttons:
        try:
            click_first(
                driver,
                [
                    (By.XPATH, f"//button[normalize-space()='{text}']"),
                    (By.XPATH, f"//*[normalize-space()='{text}']"),
                ],
                seconds=3,
            )
        except TimeoutException:
            continue


def open_create_dialog(driver: WebDriver) -> None:
    driver.get(INSTAGRAM_HOME_URL)
    dismiss_optional_dialogs(driver)

    click_first(
        driver,
        [
            (By.XPATH, "//*[@aria-label='New post']/ancestor::*[@role='button'][1]"),
            (By.XPATH, "//*[@aria-label='Create']/ancestor::*[@role='button'][1]"),
            (By.XPATH, "//*[normalize-space()='Create']"),
            (By.CSS_SELECTOR, "svg[aria-label='New post']"),
        ],
        seconds=30,
    )

    try:
        click_first(
            driver,
            [
                (By.XPATH, "//*[normalize-space()='Post']"),
                (By.XPATH, "//*[normalize-space()='Reel']"),
            ],
            seconds=5,
        )
    except TimeoutException:
        pass


def upload_video(driver: WebDriver, video_path: Path) -> None:
    file_input = first_present(driver, [(By.CSS_SELECTOR, "input[type='file']")], seconds=30)
    file_input.send_keys(str(video_path))

    print("Video selected. Waiting for Instagram editor...")
    first_present(
        driver,
        [
            (By.XPATH, "//*[normalize-space()='Next']"),
            (By.XPATH, "//*[normalize-space()='Crop']"),
            (By.XPATH, "//*[normalize-space()='Edit']"),
        ],
        seconds=90,
    )


def click_next_until_caption_step(driver: WebDriver) -> None:
    for _ in range(3):
        try:
            click_first(driver, [(By.XPATH, "//*[normalize-space()='Next']")], seconds=20)
            time.sleep(2)
        except TimeoutException:
            break

        try:
            first_present(
                driver,
                [
                    (By.XPATH, "//*[@aria-label='Write a caption...']"),
                    (By.XPATH, "//*[contains(@aria-label, 'caption')]"),
                    (By.XPATH, "//textarea"),
                    (By.XPATH, "//*[@contenteditable='true']"),
                ],
                seconds=5,
            )
            return
        except TimeoutException:
            continue


def fill_caption(driver: WebDriver, caption: str) -> None:
    caption_field = first_present(
        driver,
        [
            (By.XPATH, "//*[@aria-label='Write a caption...']"),
            (By.XPATH, "//*[contains(@aria-label, 'caption')]"),
            (By.XPATH, "//textarea"),
            (By.XPATH, "//*[@contenteditable='true']"),
        ],
        seconds=30,
    )

    caption_field.click()
    caption_field.send_keys(caption)


def share_or_pause(driver: WebDriver, publish: bool) -> None:
    if not publish:
        print("Dry run complete. The reel is prepared, but Share was not clicked.")
        input("Review the browser window. Press Enter to close the browser...")
        return

    input("Ready to publish. Review the reel, then press Enter to click Share...")
    click_first(
        driver,
        [
            (By.XPATH, "//*[normalize-space()='Share']"),
            (By.XPATH, "//*[normalize-space()='Publish']"),
        ],
        seconds=30,
    )
    print("Share clicked. Waiting for upload to finish...")
    first_present(
        driver,
        [
            (By.XPATH, "//*[contains(text(), 'Your reel has been shared')]"),
            (By.XPATH, "//*[contains(text(), 'Your post has been shared')]"),
            (By.XPATH, "//*[contains(text(), 'Reel shared')]"),
        ],
        seconds=180,
    )


def read_caption(args: argparse.Namespace) -> str:
    if args.caption and args.caption_file:
        raise InstagramUploadError("Use either --caption or --caption-file, not both.")

    if args.caption_file:
        return Path(args.caption_file).read_text(encoding="utf-8").strip()

    if args.caption:
        return args.caption.strip()

    raise InstagramUploadError("Caption is required. Pass --caption or --caption-file.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a prepared video as an Instagram Reel using Selenium."
    )
    parser.add_argument("video", help="Path to the prepared .mp4 video.")
    parser.add_argument("--caption", help="Caption text to paste into Instagram.")
    parser.add_argument("--caption-file", help="UTF-8 text file with the caption.")
    parser.add_argument(
        "--profile-dir",
        default=".selenium/instagram_chrome_profile",
        help="Chrome profile dir. Reusing it keeps Instagram login cookies.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually click Share after a final manual confirmation.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headless. Not recommended for Instagram.",
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Do not ask for credentials. Log in manually in the opened browser.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        raise InstagramUploadError(f"Video file does not exist: {video_path}")
    if video_path.suffix.lower() not in {".mp4", ".mov"}:
        raise InstagramUploadError("Instagram Reels upload expects .mp4 or .mov.")

    caption = read_caption(args)
    profile_dir = Path(args.profile_dir).expanduser().resolve() if args.profile_dir else None

    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")

    driver = create_driver(profile_dir=profile_dir, headless=args.headless)
    try:
        if not is_logged_in(driver):
            if args.manual_login:
                wait_for_manual_login(driver)
            else:
                print(
                    "Instagram is not logged in. Enter credentials in this terminal, "
                    "or rerun with --manual-login to log in in Chrome."
                )
                username = username or input("Instagram username: ").strip()
                password = password or getpass.getpass("Instagram password: ")
                login(driver, username, password)

        open_create_dialog(driver)
        upload_video(driver, video_path)
        click_next_until_caption_step(driver)
        fill_caption(driver, caption)
        share_or_pause(driver, publish=args.publish)
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstagramUploadError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
