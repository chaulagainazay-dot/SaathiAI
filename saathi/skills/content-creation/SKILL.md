---
name: content-creation
description: Rules and templates for creating pielts / Mr. Yeti social content — Facebook, Instagram, YouTube Shorts, blogs. Load when Ajay asks for any post, caption, script, story, or video content.
triggers: [post, caption, script, story, facebook, instagram, youtube, reel, short, video, blog, content, yeti, mr yeti, publish]
---

# Content Creation Skill — pielts / Mr. Yeti

## Who you're writing for
- **Brand:** pielts (https://pielts.web.app) — IELTS practice app
- **Persona:** Mr. Yeti — friendly, knowledgeable IELTS teacher. Large white-furred yeti, round black glasses, brown tweed blazer, navy polka-dot tie.
- **Audience:** IELTS students aged 18-35, English learners preparing for study abroad
- **Tone:** warm, encouraging, practical — like a smart friend who knows IELTS inside out
- **Language rule:** ALL generated content MUST be in English only. Never Chinese, Hindi, or Nepali in the post itself.

## Platform templates

### Facebook Post
- Hook (1 line that stops the scroll) — question, surprising fact, or relatable struggle
- Body (3-5 short paragraphs or bullet points) — value-dense, IELTS tip or insight
- CTA (1 line) — "Try it free at pielts.web.app" or "Comment your band score goal 👇"
- Hashtags (5-8): #IELTS #IELTSTips #IELTSPreparation #EnglishLearning #StudyAbroad #pielts #MrYeti

### Instagram Caption
- First line = hook (shows before "more")
- 3-5 punchy lines of value
- CTA: "Link in bio → pielts.web.app"
- Hashtags (10-15) at end: mix of broad (#IELTS) + niche (#IELTSWritingTask2 #BandScore7)

### YouTube Short / Reel Script (60 seconds max)
```
[0-3s]  HOOK — shocking stat or question (spoken on camera)
[3-15s] PROBLEM — relatable IELTS struggle
[15-45s] TIP — 1 clear actionable tip with example
[45-55s] DEMO — quick on-screen example or visual
[55-60s] CTA — "Practice free at pielts.web.app, link below"
```

### YouTube Long Video Description
```
[Title formula]: "IELTS [Task/Skill] — [Specific Tip] | Band [X] Strategy"
[Description]:
Line 1-2: What this video teaches (include keyword)
Line 3: "Practice for free → https://pielts.web.app"
---
TIMESTAMPS:
0:00 Introduction
...
---
TAGS: IELTS, IELTS Writing, IELTS Speaking, Band 7, Band 8, pielts, Mr Yeti
```

### Blog Post (for pielts.web.app/blog)
- Title: SEO keyword first — "IELTS Writing Task 2: How to Score Band 7+"
- Intro (100 words): hook + what reader will learn
- 3-5 H2 sections with practical tips + examples
- Conclusion + CTA: link to pielts.web.app practice page
- Meta description (under 155 chars): include "IELTS" keyword

## Mr. Yeti image prompt (when generating images)
Use style: `yeti_post` or `yeti_thumbnail` in the image endpoint.
Include topic-specific context: "Mr. Yeti [action] [setting related to IELTS topic]"
The locked look is enforced server-side — just describe the scene.

## Content calendar rule
- 1 YouTube Short per day (morning prep by 8am, auto-post at 8pm)
- 1 Facebook post per day
- 1 Instagram post every 2 days
- 1 blog post per week
- Always include https://pielts.web.app in every piece

## Quality checklist before handing to Ajay
- [ ] Written in English only
- [ ] Hook in first line
- [ ] Clear CTA with pielts.web.app link
- [ ] Relevant hashtags included
- [ ] No tool-call errors or explanation text included
