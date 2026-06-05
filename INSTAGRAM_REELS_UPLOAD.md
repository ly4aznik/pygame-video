# Instagram Reels upload automation

This helper uploads a prepared `.mp4` or `.mov` file to Instagram Reels with a prepared caption.

## Setup

```powershell
python -m pip install -r requirements.txt
```

Selenium Manager will try to find or download the right ChromeDriver automatically.

## Prepare a caption

Create a UTF-8 text file, for example `caption.txt`:

```text
Pick your color before the battle begins.
Only one snake can claim the arena. Who are you betting on?

#snakegame #simulation #pygame #gamedev #reels
```

## Dry run

Dry run selects the video and fills the caption, but does not click Share.

```powershell
python instagram_reels_uploader.py `
  "ai_light_snake_capture\window_recordings\light_snakes_20260604_135548_01\light_snakes_window.mp4" `
  --caption-file caption.txt
```

## Publish

This still pauses before the final Share click so you can review the browser.

```powershell
$env:INSTAGRAM_USERNAME = "your_username"
$env:INSTAGRAM_PASSWORD = "your_password"

python instagram_reels_uploader.py `
  "ai_light_snake_capture\window_recordings\light_snakes_20260604_135548_01\light_snakes_window.mp4" `
  --caption-file caption.txt `
  --publish
```

The script stores login cookies in `.selenium/instagram_chrome_profile`, so the next run usually does not need another login.

Instagram may still show 2FA, captcha, or account confirmation screens. Finish those manually in the opened browser, then return to the terminal.
