# The Mr. Yeti Bible

The single source of truth for who Mr. Yeti is. Every renderer — the current PIL
scene cards, and future Flux / HyperFrames / Runway / HeyGen — receives the same
reference via `saathi/character.py` (`visual_prefix()`, `scene_prompt()`).
Consistency is what turns a mascot into a brand: change the character **here once**
and every output follows.

## Who he is
- **Biography:** A warm, patient Himalayan yeti who left the mountains to become the
  world's friendliest IELTS teacher. He believes anyone can reach Band 9.
- **Personality:** warm · encouraging · patient · gently funny · never condescending.
- **Teaching philosophy:** One clear idea per lesson, a real example, then a tiny
  action. Celebrate small wins; normalise mistakes as part of learning.
- **Catchphrases:** "Let's make this simple." · "You've got this, my friend." ·
  "One small step today." · "See? Not so scary."

## How he looks
- **Appearance:** friendly Himalayan yeti, soft white-and-cream fur (`#F4F1EA`),
  large kind dark eyes, round glasses, neat teal scarf, wooden pointer.
- **Wardrobe:** round glasses + teal scarf, sometimes a cardigan.
- **Props:** wooden pointer · chalk · a warm mug labelled "Band 9" · a small globe.
- **Classroom:** cosy wooden room, green chalkboard, warm lamps, small bookshelf,
  a window showing snowy peaks.

## How he sounds
- **Voice:** friendly, calm, clear. Kokoro voice `af_heart` (draft tier).
- **Chain:** Kokoro → OpenAI → ElevenLabs (premium, v0.5).

## How it's shot
- **Style:** Pixar-quality 3D, warm soft lighting, shallow depth of field.
- **Camera:** slow zoom · gentle pan · steady medium shot at the board.
- **Animation rules:** no jump cuts · soft easing · expressions match the lesson's emotion.

## Brand palette
| Role | Hex |
|------|-----|
| Primary (purple) | `#6C3FCF` |
| Accent (teal) | `#00BFA5` |
| Dark | `#1a1a2e` |
| Fur | `#F4F1EA` |

> When a v0.5 Visual Engine (Flux with character consistency) lands, this Bible is
> the reference image + prompt seed. Nothing downstream changes but the renderer.
