# Design Guide: Calm Reels Simulation Games

Use this guide when creating similar autonomous pygame simulations so they feel like one visual series.

## Format

- Target a vertical canvas for short videos.
- Default window size: `360x640`.
- Recording/export target: `1080x1920` when using external tools.
- Keep the main game field centered horizontally.
- Leave clear space above for title/subtitle/timer and below for the score table.

## Visual Mood

- The style should be calm, bright, minimal, and readable.
- Avoid dark cyberpunk themes, neon overload, heavy gradients, and noisy backgrounds.
- Prefer clean shapes, soft colors, thin borders, and simple motion.
- The viewer should understand the simulation without reading a long explanation.

## Palette

Use this palette as the default base:

```python
BG = (246, 248, 242)        # warm off-white page background
PANEL = (255, 255, 250)     # soft white UI panels
GRID = (222, 228, 218)      # pale grid lines
TEXT = (42, 50, 62)         # dark graphite text
MUTED = (126, 137, 139)     # secondary text
DANGER = (210, 93, 96)      # calm red for death/recording/error
```

Entity colors should be pastel but distinct:

```python
YELLOW = (221, 177, 76)
GREEN = (104, 166, 129)
CORAL = (198, 104, 101)
BLUE = (92, 139, 184)
PURPLE = (150, 124, 180)
```

## Layout

- Top header:
  - Title in large bold text.
  - Subtitle below in muted blue/gray.
  - Optional timer below subtitle.
- Center:
  - Game field with a light panel background.
  - Thin border around the game field.
  - Subtle grid lines only; avoid high-contrast grid.
- Bottom:
  - Compact score table.
  - Use columns for name, behavior/AI type, score, size/length, and status.
  - Keep it dense and readable.

## Game Field

- Prefer fewer, larger cells over many tiny cells for mobile video readability.
- Current snake game field:

```python
CELL_SIZE = 15
GRID_COLS = 15
GRID_ROWS = 22
```

- Use rounded rectangles or circles for entities.
- Keep all active objects readable at phone screen size.

## Typography

- Use simple system fonts such as Arial.
- Prefer bold for labels, names, and table values.
- Keep text short:
  - Title: 2-4 words.
  - Subtitle: one question or short hook.
  - Status: `alive`, `dead`, `WINNER`, `TIME LIMIT`.
- Avoid explanatory paragraphs inside the app.

## Motion And Effects

Effects should be visible but not flashy:

- Soft particle burst when collecting an item.
- Short death flash when an entity dies.
- Small trail behind moving entities.
- Gentle pulse/glow for collectible items.

Avoid:

- Full-screen explosions.
- Screen shake.
- Harsh flashes.
- Dense particle clouds that hide the simulation.

## HUD Rules

- Every competing entity should have:
  - A name.
  - A unique color.
  - A visible status.
  - A score or progress metric.
- Labels above moving entities should be small and unobtrusive.
- The score table should stay stable; avoid resizing rows/columns during gameplay.

## End Screen

- Use a soft overlay, not a dark blackout.
- Show:
  - `WINNER`
  - winner name
  - strategy/type
  - score and size
  - finish reason
  - restart hint
- Keep the final screen centered and readable in a vertical crop.

## Recording Style

- When recording, capture the app window externally rather than saving pygame frames.
- Do not show mouse cursor in the recording.
- Stop recording automatically when the match ends.
- If music is added, do it as post-processing and keep the original silent video.
- Use legally licensed music and keep attribution text with the project.

## Interaction

Keep controls minimal:

- `R`: restart / new match.
- `SPACE`: pause.
- `S`: screenshot.

The simulation should run autonomously without user input.

## Code Organization

For similar games, keep the same broad structure:

- Constants at the top for size, colors, speed, counts.
- Dataclasses for simple visual objects.
- Entity class for each competitor.
- Strategy functions or strategy classes.
- One `Game` class for lifecycle, input, updates, rendering, and recording hooks.

Keep comments short and practical, especially near strategy behavior so it is easy to tune.

## Design Checklist

Before publishing or recording:

- The field fits the vertical canvas.
- The score table is visible and not cramped.
- Entity colors are distinct.
- Labels do not overlap too much.
- The winner screen is readable.
- The simulation is understandable without narration.
- The output has a calm, bright, consistent look.
