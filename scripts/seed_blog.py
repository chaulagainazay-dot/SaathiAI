#!/usr/bin/env python3
"""
seed_blog.py — Seeds 20 SEO blog articles to pielts Firebase Realtime Database.

Schema (matches useBlogStore.js):
  { slug, title, content, excerpt, published, ts, updated }

Run:
  python3 ~/SaathiAI/scripts/seed_blog.py
  python3 ~/SaathiAI/scripts/seed_blog.py --dry-run
  python3 ~/SaathiAI/scripts/seed_blog.py --skip-existing
"""

import argparse
import json
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import firebase_admin
from firebase_admin import credentials, db

# ── Config ──────────────────────────────────────────────────────────────────
SA_KEY_PATH = "/Users/macbookpro/SaathiAI/scripts/pielts-sa-key.json"
DATABASE_URL = "https://ielts-and-language-practice-default-rtdb.firebaseio.com"


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower().strip())).strip("-")[:80]


# ── Articles ─────────────────────────────────────────────────────────────────
ARTICLES = [
    {
        "title": "IELTS Band 9: Is It Possible and How Do You Get There?",
        "excerpt": "Band 9 is achievable — but only with the right strategy. Here is exactly what examiners look for at the top score.",
        "content": (
            "Band 9 means 'Expert user: full operational command of the language'. Fewer than 1% of test-takers reach it, "
            "but it is a real target if you are already at Band 7–8 and willing to train deliberately.\n\n"
            "**What separates Band 8 from Band 9**\n\n"
            "At Band 8 you make rare errors; at Band 9 you make almost none under exam pressure. The gap is not vocabulary size — "
            "it is consistency. A Band 9 speaker can speak for two minutes on an abstract topic (Part 3) with natural fluency, "
            "precise word choice, and no noticeable hesitation.\n\n"
            "**Speaking: the micro-skills that matter**\n\n"
            "1. Use discourse markers naturally — 'What I find interesting is…', 'Having said that…'\n"
            "2. Self-correct mid-sentence: examiners reward it as evidence of monitoring.\n"
            "3. Vary your intonation. Monotone delivery caps Pronunciation at Band 7.\n\n"
            "**Writing: what Band 9 essays actually look like**\n\n"
            "- Zero article errors (a/an/the is the most common grammar trap).\n"
            "- Cohesion devices are invisible — the essay flows without mechanical 'Firstly… Secondly…'.\n"
            "- Every body paragraph has a clear claim, an explanation, and a concrete example.\n\n"
            "**Listening and Reading at Band 9**\n\n"
            "You need 39–40 correct answers (Listening) and 38–40 (Academic Reading). The only way is timed practice with "
            "genuine Academic materials — newspapers like The Economist, nature.com, and BBC Future.\n\n"
            "**The fastest path from Band 8 to Band 9**\n\n"
            "Record your speaking answers and transcribe them. Every filler, false start, and grammar slip becomes visible. "
            "Fix the top three patterns. Repeat weekly. Use pielts to benchmark your writing with instant band estimates "
            "so you can measure progress rather than guess."
        ),
    },
    {
        "title": "IELTS Reading: 7 Strategies to Finish Every Section on Time",
        "excerpt": "Running out of time on IELTS Reading is the single most common reason for Band 6 instead of Band 7. Here are 7 strategies that fix it.",
        "content": (
            "The IELTS Academic Reading test gives you 60 minutes for three passages and 40 questions. Most test-takers "
            "spend too long on the first passage and rush the last one. These seven strategies fix the time problem.\n\n"
            "**1. Skim the passage in 90 seconds**\n"
            "Read only the first sentence of each paragraph. This gives you a mental map so you know where to look.\n\n"
            "**2. Read the questions before the passage**\n"
            "Knowing what you are looking for turns reading into a treasure hunt. Underline the key noun in each question.\n\n"
            "**3. Use the paragraph headings question as your guide**\n"
            "If there is a 'matching headings' task, do it first — it forces you to read each paragraph carefully and builds your map.\n\n"
            "**4. Spend 20 minutes per passage — set a mental alarm**\n"
            "If you hit 20 minutes and are still on passage one, move on. Unanswered questions still get a guess.\n\n"
            "**5. True/False/Not Given: 'Not Given' means absent, not false**\n"
            "The most common mistake is marking 'False' when the passage simply does not mention something. 'Not Given' means "
            "the passage is silent on the point.\n\n"
            "**6. Matching information questions: scan, do not read**\n"
            "These questions have the answer spread across the passage. Use keywords to scan — read only the relevant sentence.\n\n"
            "**7. Never leave a blank**\n"
            "There is no negative marking in IELTS. Always guess. Choose B if you have no idea."
        ),
    },
    {
        "title": "IELTS Listening Band 8: Precision Habits for Top Scores",
        "excerpt": "Band 8 in IELTS Listening requires 36–37 correct answers. These precision habits eliminate the small errors that cost you marks.",
        "content": (
            "IELTS Listening is the skill most test-takers underestimate. Unlike Speaking, there is no examiner watching you — "
            "you only need to write the right word in the right box. But 'small' errors like spelling mistakes or misheard numbers "
            "drop your band fast.\n\n"
            "**Habit 1: Predict before you listen**\n"
            "In the 30 seconds before each section plays, read the questions and predict the answer type: a number? a name? "
            "a place? This primes your brain to catch the right information.\n\n"
            "**Habit 2: Listen for paraphrases, not exact words**\n"
            "The recording almost never uses the same words as the question. 'A place to store documents' in the question "
            "might become 'a filing room' in the recording.\n\n"
            "**Habit 3: Spell proper nouns carefully**\n"
            "The recording often spells out names. Write every letter. A misspelled name is a wrong answer even if the "
            "phonetics are correct.\n\n"
            "**Habit 4: Watch for plural traps**\n"
            "If the answer is a noun and you hear it in plural form, write the plural. 'Documents' ≠ 'document'.\n\n"
            "**Habit 5: Do not panic if you miss one answer**\n"
            "Stay with the recording. Look at the next question immediately. Missing one answer and spending 10 seconds "
            "trying to recover it causes you to miss the next two answers too.\n\n"
            "**Habit 6: Use the transfer time wisely**\n"
            "You have 10 minutes to transfer answers to the answer sheet. Check spelling on every word, not just names."
        ),
    },
    {
        "title": "IELTS Writing Task 1 Academic: How to Describe Any Graph",
        "excerpt": "A reliable 4-step formula for describing any bar chart, line graph, pie chart, or table in IELTS Academic Writing Task 1.",
        "content": (
            "Writing Task 1 Academic asks you to describe a graph, chart, diagram, or map in at least 150 words. "
            "The key skill is selecting and reporting the most important features — not describing every single number.\n\n"
            "**The 4-step formula**\n\n"
            "**Step 1: Introduction (1–2 sentences)**\n"
            "Paraphrase the title. 'The bar chart shows the proportion of adults in four countries who used the internet "
            "between 2000 and 2020.' Never copy the title word for word.\n\n"
            "**Step 2: Overview (2–3 sentences)**\n"
            "Describe the two or three most striking trends. 'Overall, internet use rose in all four countries, with Country A "
            "showing the steepest increase.' This is the paragraph examiners look for first.\n\n"
            "**Step 3: Body paragraph 1 — Group the data**\n"
            "Group countries or categories by similarity. 'Countries A and B started with low usage (under 10%) but grew "
            "dramatically to 80% and 65% respectively by 2020.'\n\n"
            "**Step 4: Body paragraph 2 — The contrasting group**\n"
            "'Countries C and D began with higher usage but grew more slowly, reaching 55% and 48% by the end of the period.'\n\n"
            "**Key language to use**\n\n"
            "- Trends: rose sharply / fell gradually / remained stable / fluctuated\n"
            "- Comparisons: higher than / twice as much as / approximately / roughly\n"
            "- Time: between 2000 and 2020 / over the period / by 2020\n\n"
            "**What to avoid**\n\n"
            "Do not give personal opinions. Do not invent reasons ('This is because…'). Do not describe every data point — "
            "select only the most significant ones."
        ),
    },
    {
        "title": "IELTS General Training Writing Task 1: How to Write a Formal Letter",
        "excerpt": "A step-by-step guide for writing a formal letter in IELTS General Training that gets Band 7 or above.",
        "content": (
            "In IELTS General Training Writing Task 1, you write a letter. The three types are: formal (to a company/authority), "
            "semi-formal (to someone you know professionally), and informal (to a friend). This guide focuses on formal letters.\n\n"
            "**Structure of a formal letter**\n\n"
            "1. **Salutation**: Dear Sir or Madam (if you do not know the name); Dear Mr/Ms [Name] (if given).\n"
            "2. **Opening purpose**: State why you are writing in the first sentence. 'I am writing to complain about…'\n"
            "3. **Three bullet-point paragraphs**: The task gives you three bullet points. Each one becomes a paragraph.\n"
            "4. **Closing**: 'I look forward to hearing from you.' or 'I would be grateful for a prompt response.'\n"
            "5. **Sign-off**: 'Yours faithfully' (if you used Dear Sir/Madam); 'Yours sincerely' (if you used a name).\n\n"
            "**Language for formal letters**\n\n"
            "- Avoid contractions: 'I would' not 'I'd'; 'I am' not 'I'm'.\n"
            "- Use polite indirect forms: 'I would be grateful if you could…' not 'Please do…'\n"
            "- Be specific: include dates, reference numbers, and exact names when given.\n\n"
            "**Common mistakes**\n\n"
            "- Writing too informally (using casual vocabulary).\n"
            "- Not covering all three bullet points.\n"
            "- Writing fewer than 150 words — there is a word-count penalty."
        ),
    },
    {
        "title": "IELTS Vocabulary: 50 Linking Words That Raise Your Band Score",
        "excerpt": "Using a wider range of linking words is one of the fastest ways to improve your Coherence and Cohesion score in IELTS Writing.",
        "content": (
            "Examiners assess Coherence and Cohesion (CC) as 25% of your Writing score. One key CC criterion is "
            "'uses a range of cohesive devices'. This means using linking words beyond 'because', 'so', and 'also'.\n\n"
            "**Cause and effect (beyond 'because')**\n"
            "- as a result of / owing to / due to / consequently / therefore / hence / thus / for this reason\n\n"
            "**Contrast (beyond 'but')**\n"
            "- however / nevertheless / nonetheless / despite this / on the other hand / in contrast / whereas / while / although / even though\n\n"
            "**Adding information (beyond 'also')**\n"
            "- furthermore / in addition / moreover / what is more / not only… but also / besides this\n\n"
            "**Giving examples (beyond 'for example')**\n"
            "- for instance / such as / including / in particular / to illustrate / a case in point is\n\n"
            "**Concession (admitting the other side)**\n"
            "- admittedly / granted / it is true that… however / while it is the case that…\n\n"
            "**Conclusion**\n"
            "- in conclusion / to sum up / overall / in summary / taking everything into consideration\n\n"
            "**How to use these effectively**\n\n"
            "Do not begin every sentence with a linker — that scores Band 6 for CC, not Band 7. Instead, vary your "
            "methods: sometimes use a linking word, sometimes use a pronoun ('This'), sometimes use repetition of a key noun. "
            "A mix of methods signals sophistication."
        ),
    },
    {
        "title": "How to Improve IELTS Speaking Fluency in 30 Days",
        "excerpt": "A 30-day daily practice plan that targets the exact fluency habits IELTS examiners reward.",
        "content": (
            "IELTS Speaking Fluency is measured on how smoothly you speak, not how fast. Examiners penalise long pauses "
            "and repetition, not a measured pace. This 30-day plan targets the root causes of disfluency.\n\n"
            "**Week 1: Build your answer bank**\n"
            "Every day, practise answering 5 Part 1 questions (hobbies, family, work, weather, food). Time yourself: "
            "aim for 20–30 seconds each without stopping. Do not worry about accuracy yet — just keep talking.\n\n"
            "**Week 2: Stop using filler words**\n"
            "Identify your most-used fillers ('um', 'like', 'you know'). Record yourself for 2 minutes and count them. "
            "Replace them with a 1-second pause or with discourse markers: 'Well…', 'That is a good question actually…'\n\n"
            "**Week 3: Extend your answers with PEEL**\n"
            "Point — Evidence — Explanation — Link. 'I enjoy hiking (Point). Last month I walked in the mountains outside "
            "Kathmandu (Evidence). It was challenging but cleared my mind completely (Explanation). I try to go every month "
            "if I can (Link).'\n\n"
            "**Week 4: Simulate Part 2 daily**\n"
            "Pick a Part 2 cue card, take 1 minute to prepare notes, then speak for exactly 2 minutes. Record it, "
            "transcribe the last 30 seconds, and count how many filler words appear.\n\n"
            "**Daily habit that matters most**\n"
            "Think in English for 10 minutes every morning — narrate what you are doing as you prepare breakfast or commute. "
            "This builds the mental muscle that produces automatic, fluent speech in the exam."
        ),
    },
    {
        "title": "IELTS Writing Task 2 Opinion Essay: A Template That Actually Works",
        "excerpt": "A clear, examiner-tested template for IELTS Writing Task 2 opinion essays — with annotated examples at Band 7 and Band 8.",
        "content": (
            "Opinion essays ('Do you agree or disagree?') are the most common Task 2 type. Having a reliable template "
            "means you spend your mental energy on ideas and language — not structure.\n\n"
            "**The Template**\n\n"
            "**Introduction (3 sentences)**\n"
            "1. Paraphrase the statement: 'It is often argued that…'\n"
            "2. State your position clearly: 'I fully agree with this view.' or 'While there is some merit to this claim, "
            "I believe… because…'\n"
            "3. Outline what you will discuss (optional at Band 7+).\n\n"
            "**Body paragraph 1 — Your main reason (6–8 sentences)**\n"
            "- Claim: state your first reason.\n"
            "- Explain: why is this true?\n"
            "- Example: give a specific, real-world example.\n"
            "- Result: what does this show?\n\n"
            "**Body paragraph 2 — Your second reason or a concession (6–8 sentences)**\n"
            "If you fully agree: give a second supporting reason.\n"
            "If you partially agree: 'Opponents argue that… However, this view overlooks…'\n\n"
            "**Conclusion (2–3 sentences)**\n"
            "'In conclusion, I believe… because… and… Governments/individuals/companies should therefore…'\n\n"
            "**Band 7 vs Band 8 language example**\n\n"
            "Band 7: 'Many people think technology is bad for children.'\n"
            "Band 8: 'A significant body of research suggests that excessive screen time may impair the cognitive development of young children.'\n\n"
            "The idea is the same — the language precision is different. Practise upgrading one sentence per essay."
        ),
    },
    {
        "title": "IELTS Pronunciation Guide: How Accent Affects Your Band Score",
        "excerpt": "Your accent does NOT matter for IELTS Pronunciation — but these five features do. Here is what examiners actually assess.",
        "content": (
            "A common misconception: examiners do not penalise non-native accents. An Indian, Filipino, or Nepali accent "
            "does not cost you marks. What matters is whether your speech is easy to understand.\n\n"
            "**The 5 pronunciation features examiners assess**\n\n"
            "**1. Word stress**\n"
            "English words have a stressed syllable: 'PHOtograph' not 'photoGRAPH'. Stressing the wrong syllable is the "
            "most common cause of miscommunication. Practise 10 new words per day and mark the stress.\n\n"
            "**2. Sentence stress**\n"
            "In natural English, content words (nouns, verbs, adjectives) are stressed; function words (the, is, of) are "
            "reduced. 'I WANT to LEARN to SPEAK BETTER' — not every word equal.\n\n"
            "**3. Connected speech**\n"
            "Native speakers link words: 'Did you eat?' sounds like 'Dijeet?' This is not sloppy — it is natural. "
            "Practise linking final consonants to opening vowels.\n\n"
            "**4. Intonation**\n"
            "Rising intonation for yes/no questions, falling for statements. A flat intonation sounds robotic and scores Band 6.\n\n"
            "**5. Range**\n"
            "Can you use wide intonation to show enthusiasm? Can you reduce to a near-whisper for emphasis? Range signals fluency.\n\n"
            "**How to train pronunciation**\n"
            "Shadowing: find a YouTube video with a clear English speaker, pause every sentence, and repeat with the same "
            "stress and rhythm. Do this for 10 minutes daily."
        ),
    },
    {
        "title": "IELTS vs TOEFL: Which Test Should You Take in 2025?",
        "excerpt": "A practical comparison of IELTS and TOEFL for university applications, skilled migration, and professional registration in 2025.",
        "content": (
            "If your goal is an English-speaking country's university or immigration programme, you probably need either "
            "IELTS or TOEFL. Here is how to choose.\n\n"
            "**Acceptance**\n\n"
            "- IELTS: accepted by over 11,000 organisations worldwide, including UK, Australia, Canada, New Zealand, and most "
            "EU countries. Mandatory for UK Skilled Worker visas.\n"
            "- TOEFL: preferred by many US and Canadian universities; less accepted in the UK and Australia for immigration.\n\n"
            "**Test format**\n\n"
            "IELTS has a face-to-face Speaking interview with an examiner — many test-takers find this more natural. TOEFL "
            "Speaking is recorded and scored by AI and human raters. IELTS Writing is hand-written (Paper) or typed (Computer); "
            "TOEFL Writing is always typed.\n\n"
            "**Score conversion (approximate)**\n\n"
            "| IELTS | TOEFL iBT |\n"
            "|-------|----------|\n"
            "| 5.5   | 46–59    |\n"
            "| 6.0   | 60–78    |\n"
            "| 6.5   | 79–93    |\n"
            "| 7.0   | 94–101   |\n"
            "| 7.5   | 102–109  |\n"
            "| 8.0   | 110–114  |\n\n"
            "**Which is easier?**\n\n"
            "Neither is definitively easier — they test slightly different skills. IELTS rewards handwriting speed and "
            "face-to-face conversation; TOEFL rewards integrated writing and speaking from notes. Choose based on your "
            "strengths and the requirement of the institution you are applying to."
        ),
    },
    {
        "title": "IELTS Academic vs General Training: Key Differences Explained",
        "excerpt": "Not sure which IELTS version you need? This guide explains the differences between Academic and General Training and when each is required.",
        "content": (
            "IELTS comes in two versions: Academic and General Training. They share the same Listening and Speaking tests "
            "but differ in Reading and Writing.\n\n"
            "**When to take Academic**\n\n"
            "- Undergraduate and postgraduate university admissions worldwide.\n"
            "- Professional registration for doctors, nurses, teachers, and engineers in countries like the UK, Australia, and Canada.\n\n"
            "**When to take General Training**\n\n"
            "- Skilled worker immigration to Australia, Canada, New Zealand, and the UK.\n"
            "- Work experience programmes.\n"
            "- Secondary school admissions.\n\n"
            "**Reading differences**\n\n"
            "Academic Reading uses complex texts from academic journals and magazines. General Training uses texts from "
            "advertisements, notices, workplace materials, and newspapers. General Training Reading is considered slightly "
            "easier in terms of vocabulary.\n\n"
            "**Writing differences**\n\n"
            "Academic Task 1: describe a graph, chart, diagram, or map.\n"
            "General Training Task 1: write a letter (formal, semi-formal, or informal).\n\n"
            "Task 2 (essay) is the same for both versions.\n\n"
            "**Are the scores comparable?**\n\n"
            "Yes — a Band 7 in Academic and a Band 7 in General Training represent the same level of proficiency. "
            "However, immigration authorities and universities specify which version they accept — always check before booking."
        ),
    },
    {
        "title": "How to Prepare for IELTS in 3 Months: A Week-by-Week Study Plan",
        "excerpt": "A structured 12-week IELTS study plan for working adults and students — organised by skill and week to maximise your band score.",
        "content": (
            "Three months is enough time to raise your IELTS score by one full band if you study consistently. "
            "Here is a week-by-week framework.\n\n"
            "**Months 1 (Weeks 1–4): Diagnose and build foundations**\n\n"
            "- Week 1: Take a full practice test. Score it. Identify your weakest skill.\n"
            "- Week 2: Vocabulary — learn 10 academic words per day using spaced repetition.\n"
            "- Week 3: Grammar — review common error types: articles, tense consistency, subject-verb agreement.\n"
            "- Week 4: Reading — practise skimming and scanning on one passage per day.\n\n"
            "**Month 2 (Weeks 5–8): Skill drills**\n\n"
            "- Week 5–6: Writing — write one Task 2 essay per day and get feedback. Use pielts for instant band estimates.\n"
            "- Week 7: Listening — complete one full Listening test under timed conditions every other day.\n"
            "- Week 8: Speaking — record 3 Part 2 answers per day and listen back.\n\n"
            "**Month 3 (Weeks 9–12): Exam simulation**\n\n"
            "- Week 9–10: Take 2 full practice tests per week under exam conditions.\n"
            "- Week 11: Review every wrong answer. Build a personal error log.\n"
            "- Week 12: Light review only. Sleep 8 hours the night before the exam.\n\n"
            "**Time commitment**\n\n"
            "45–60 minutes per day is more effective than 4-hour weekend sessions. Consistency compounds."
        ),
    },
    {
        "title": "IELTS Writing Task 2: How to Write a Problem-Solution Essay",
        "excerpt": "Problem-solution essays are one of the most predictable IELTS Task 2 types. Here is the exact structure and language to get Band 7+.",
        "content": (
            "Problem-solution essays ask you to identify the causes or problems related to an issue and propose solutions. "
            "Common topics include: pollution, urbanisation, rising crime, youth unemployment, social media addiction.\n\n"
            "**The structure**\n\n"
            "**Introduction**\n"
            "Paraphrase the issue and state that you will discuss the main problems and solutions.\n"
            "'The rapid growth of urban populations has led to serious challenges in many cities. This essay will examine "
            "the key problems this creates and suggest practical solutions.'\n\n"
            "**Body paragraph 1 — The problems**\n"
            "Identify two problems and explain each one. Use specific examples.\n"
            "'The most significant problem is the shortage of affordable housing. As more people move to cities seeking work, "
            "demand for housing far outstrips supply, pushing prices beyond the reach of low-income families.'\n\n"
            "**Body paragraph 2 — The solutions**\n"
            "Match each solution to the problem it addresses.\n"
            "'To tackle the housing shortage, governments could incentivise developers to build affordable units by offering "
            "tax relief on low-cost housing projects…'\n\n"
            "**Conclusion**\n"
            "Restate the main problems and solutions in different words. End with a recommendation.\n\n"
            "**Key language**\n\n"
            "Problems: lead to / result in / cause / give rise to / contribute to\n"
            "Solutions: address / tackle / mitigate / reduce / alleviate / deal with"
        ),
    },
    {
        "title": "IELTS Speaking Part 3: How to Answer Abstract Questions Confidently",
        "excerpt": "Part 3 questions test your ability to discuss ideas, not just personal experience. Here is how to give sophisticated, extended answers.",
        "content": (
            "IELTS Speaking Part 3 is the hardest section because questions are abstract: 'Do you think technology has "
            "changed the way people socialise?' These are not about your personal life — they ask for opinions, analysis, "
            "and speculation.\n\n"
            "**The examiner is testing**\n\n"
            "- Can you speak at length without the examiner prompting?\n"
            "- Do you use a range of vocabulary for opinion, certainty, and hedging?\n"
            "- Can you discuss two sides of an issue?\n\n"
            "**A 4-part answer structure**\n\n"
            "1. State your position: 'I think technology has fundamentally changed socialising, yes.'\n"
            "2. Give a reason: 'Social media allows people to maintain friendships across distances that would have faded naturally before.'\n"
            "3. Acknowledge complexity: 'That said, there is growing evidence that online interaction is replacing face-to-face "
            "contact, which can reduce empathy.'\n"
            "4. Land on your view: 'On balance, I believe the benefits outweigh the costs, provided people are conscious about "
            "how much time they spend online.'\n\n"
            "**Useful language for Part 3**\n\n"
            "- Hedging: 'It seems to me that…', 'I would argue…', 'It could be said that…'\n"
            "- Concession: 'While I accept that…', 'Despite this…'\n"
            "- Speculation: 'If this trend continues…', 'In the long run…'\n\n"
            "**Common mistake**\n\n"
            "Giving very short answers. Part 3 expects 4–6 sentences per answer. If you finish in 2 sentences, ask yourself "
            "'why?' and 'is this always the case?' to extend."
        ),
    },
    {
        "title": "IELTS Listening Section 4: How to Handle Monologues and Lectures",
        "excerpt": "Section 4 is the hardest IELTS Listening section. These strategies help you keep up with academic monologues and score full marks.",
        "content": (
            "Section 4 of IELTS Listening is a monologue on an academic topic — a university lecture or talk. It is the "
            "longest and most complex section, and there are no pauses between questions.\n\n"
            "**Why Section 4 is hard**\n\n"
            "- No pauses in the recording.\n"
            "- Academic vocabulary you may not know.\n"
            "- Complex sentence structures with multiple clauses.\n"
            "- Answers are often paraphrases, not repeated words.\n\n"
            "**Strategy 1: Preview the questions carefully**\n"
            "Before Section 4 plays, you get time to preview the questions. Read all of them quickly and underline "
            "the key nouns. This tells you the topic and the type of information you need.\n\n"
            "**Strategy 2: Use the flow of the lecture**\n"
            "Academic lectures follow a structure: introduction → first point → second point → conclusion. If you lose "
            "track, listen for signpost language: 'Moving on to…', 'Another key point is…', 'To summarise…'\n\n"
            "**Strategy 3: Do not panic at unknown vocabulary**\n"
            "The answer may be a common word you know; the surrounding context may use technical vocabulary. Focus on "
            "the 3–4 words immediately around where the answer should be.\n\n"
            "**Strategy 4: Write while you listen**\n"
            "Do not wait until you have heard the full answer. Start writing as soon as you hear something relevant. "
            "You can correct spelling during the transfer time.\n\n"
            "**Training tip**\n"
            "Listen to TED Talks and take notes on the main points. This builds the exact skill Section 4 tests: "
            "capturing key information from an academic monologue."
        ),
    },
    {
        "title": "IELTS Grammar: The 8 Most Common Mistakes and How to Fix Them",
        "excerpt": "Eight grammar errors appear in almost every IELTS Writing script below Band 7. Fixing them is the fastest way to raise your Grammatical Range and Accuracy score.",
        "content": (
            "Grammatical Range and Accuracy (GRA) is 25% of your Writing score. Examiners look for a mix of simple "
            "and complex sentences with few errors. These eight mistakes appear most often.\n\n"
            "**1. Article errors (a/an/the)**\n"
            "Use 'a/an' for first mention or non-specific nouns. Use 'the' for second mention or specific nouns. "
            "'A study was published. The study showed…'\n\n"
            "**2. Subject-verb agreement**\n"
            "'The number of students is increasing.' (not 'are').\n"
            "'A range of factors affects this.' (not 'affect').\n\n"
            "**3. Wrong tense**\n"
            "Use past tense for graphs with a defined time period that has ended: 'Sales rose in 2015'. "
            "Use present tense for general truths: 'Exercise improves mental health.'\n\n"
            "**4. Countable/uncountable nouns**\n"
            "Information, advice, research, evidence, knowledge, furniture — these are uncountable. "
            "Never write 'informations', 'advices', 'researches'.\n\n"
            "**5. Dangling modifiers**\n"
            "Wrong: 'Being a student, the exam was hard.' (The exam is not a student.)\n"
            "Right: 'Being a student, I found the exam hard.'\n\n"
            "**6. Run-on sentences**\n"
            "Wrong: 'The population is growing, cities are getting more crowded.'\n"
            "Right: 'The population is growing; as a result, cities are getting more crowded.'\n\n"
            "**7. Incorrect use of 'which' and 'that'**\n"
            "'That' defines (restrictive): 'The report that was published last year…'\n"
            "'Which' adds information (non-restrictive): 'The report, which was published last year, showed…'\n\n"
            "**8. Parallelism errors**\n"
            "Wrong: 'She enjoys swimming, running, and to cycle.'\n"
            "Right: 'She enjoys swimming, running, and cycling.'"
        ),
    },
    {
        "title": "How to Write an IELTS Discussion Essay (Both Views Essay) at Band 7",
        "excerpt": "Discussion essays ask you to present BOTH sides before giving your opinion. Here is the structure and language to hit Band 7.",
        "content": (
            "Discussion essays ('Discuss both views and give your own opinion') are one of the trickiest Task 2 types "
            "because test-takers often forget to state their own opinion, or they give it too late.\n\n"
            "**Common mistake**\n\n"
            "Writing 2 body paragraphs (one for each view) without stating your own view in the introduction or conclusion. "
            "This scores Band 5 for Task Response because the question is not fully answered.\n\n"
            "**The structure**\n\n"
            "**Introduction**\n"
            "1. Paraphrase the topic.\n"
            "2. State BOTH views exist.\n"
            "3. State YOUR view clearly. ('Although some argue X, I believe Y is more persuasive because…')\n\n"
            "**Body paragraph 1 — View 1 (the view you find less persuasive)**\n"
            "Present the opposing view fairly, with a reason and example. Do not attack it — just describe it.\n\n"
            "**Body paragraph 2 — View 2 (your preferred view)**\n"
            "Present this view more fully — give two reasons and an example. Since this is your view, develop it more.\n\n"
            "**Conclusion**\n"
            "Restate both views. Restate your position. You can add a recommendation.\n\n"
            "**Language for discussing two views**\n\n"
            "- Presenting view 1: 'Those who believe… argue that…', 'Proponents of this position claim…'\n"
            "- Transitioning: 'On the other hand…', 'From a different perspective…'\n"
            "- Presenting your view: 'Personally, I am more persuaded by…', 'In my view, the stronger argument is…'"
        ),
    },
    {
        "title": "IELTS Cue Card Topics 2025: The 20 Most Common Themes",
        "excerpt": "These 20 cue card themes cover 80% of what appears in the IELTS Speaking Part 2 exam. Prepare a strong answer for each.",
        "content": (
            "IELTS Speaking Part 2 gives you a cue card with a topic and 3–4 bullet points. You get 1 minute to prepare "
            "and must speak for 1–2 minutes. These 20 themes appear most frequently.\n\n"
            "**People**\n"
            "1. Describe someone who has influenced you.\n"
            "2. Describe a famous person you admire.\n"
            "3. Describe a teacher who made an impact on you.\n\n"
            "**Places**\n"
            "4. Describe a place you have visited that impressed you.\n"
            "5. Describe a city you would like to live in.\n"
            "6. Describe a park or outdoor space you enjoy.\n\n"
            "**Objects**\n"
            "7. Describe a gift you have given or received.\n"
            "8. Describe a piece of technology you use often.\n"
            "9. Describe a book that affected you.\n\n"
            "**Events**\n"
            "10. Describe a celebration or festival you attended.\n"
            "11. Describe a time you achieved a goal.\n"
            "12. Describe a memorable journey or trip.\n\n"
            "**Activities**\n"
            "13. Describe a sport or physical activity you enjoy.\n"
            "14. Describe a skill you have learned recently.\n"
            "15. Describe a hobby you have.\n\n"
            "**Abstract/Ideas**\n"
            "16. Describe a tradition in your culture.\n"
            "17. Describe a time when you helped someone.\n"
            "18. Describe a piece of news that interested you.\n"
            "19. Describe a goal you want to achieve in the future.\n"
            "20. Describe an environment or nature experience you remember.\n\n"
            "**Preparation tip**\n\n"
            "For each theme, prepare a 'bank' answer: a real personal story with sensory details, feelings, and a "
            "reflection. The same story can be adapted across multiple cue card prompts."
        ),
    },
    {
        "title": "IELTS Writing: How to Paraphrase Without Plagiarising the Question",
        "excerpt": "Paraphrasing the question is the first skill you demonstrate in Task 2. Here is how to do it well without copying words.",
        "content": (
            "Every IELTS Writing Task 2 begins with an instruction like: 'Some people believe that universities should "
            "focus only on academic subjects rather than preparing students for employment. To what extent do you agree?'\n\n"
            "Your introduction must paraphrase this — not copy it. Copying the exact words scores Band 5 for Task Response "
            "because the examiner cannot tell if you understand it.\n\n"
            "**4 paraphrasing techniques**\n\n"
            "**1. Synonym substitution**\n"
            "universities → higher education institutions / tertiary education\n"
            "focus → concentrate / prioritise\n"
            "academic subjects → theoretical disciplines / scholarly study\n\n"
            "**2. Change the grammatical structure**\n"
            "Original: 'Universities should focus only on academic subjects.'\n"
            "Paraphrased: 'Whether higher education institutions ought to restrict their curriculum to scholarly disciplines is a matter of debate.'\n\n"
            "**3. Change the perspective**\n"
            "Original: 'Preparing students for employment.'\n"
            "Paraphrased: 'developing graduates' professional readiness.'\n\n"
            "**4. Combine techniques**\n"
            "Original: 'Some people believe that universities should focus only on academic subjects rather than preparing "
            "students for employment.'\n"
            "Paraphrased: 'There is a view in some quarters that tertiary institutions should prioritise theoretical "
            "learning over equipping graduates with practical vocational skills.'\n\n"
            "**What not to do**\n\n"
            "- Do not change every single word — natural paraphrasing keeps some words the same.\n"
            "- Do not add your opinion in the first sentence.\n"
            "- Do not make the paraphrase longer than 2 sentences."
        ),
    },
    {
        "title": "IELTS Self-Study Guide: Free Resources That Actually Help You Improve",
        "excerpt": "The best free IELTS preparation resources in 2025 — organised by skill so you can build a self-study plan without spending money.",
        "content": (
            "You do not need expensive courses to prepare for IELTS. These free resources cover every skill.\n\n"
            "**Official free resources**\n\n"
            "- **IELTS.org sample test materials**: Free sample papers for both Academic and General Training. Use these "
            "as your primary timed practice material.\n"
            "- **British Council LearnEnglish**: Free grammar exercises, vocabulary activities, and listening practice "
            "aligned with IELTS level.\n\n"
            "**Listening practice (free)**\n\n"
            "- BBC Learning English: daily podcasts and YouTube videos with transcripts.\n"
            "- TED Talks (ted.com): academic lectures at the level of Section 4.\n"
            "- The Economist audio articles: complex vocabulary in context.\n\n"
            "**Reading practice (free)**\n\n"
            "- Wikipedia's 'Featured Articles': well-structured academic writing.\n"
            "- New Scientist and BBC Future: complex non-fiction at IELTS Academic level.\n\n"
            "**Writing practice (free)**\n\n"
            "- **pielts.web.app**: instant AI-powered band estimate for your essays with sentence-level feedback.\n"
            "- r/IELTS on Reddit: community feedback on writing samples.\n\n"
            "**Speaking practice (free)**\n\n"
            "- iTalki (community tutor sessions can be under $5).\n"
            "- Speeko app: structured speaking exercises.\n"
            "- Recording yourself and using pielts or a transcription app to review.\n\n"
            "**How to build a free study plan**\n\n"
            "1. Take an official sample test to get a baseline.\n"
            "2. Focus 60% of study time on your weakest skill.\n"
            "3. Use pielts to measure Writing progress weekly.\n"
            "4. Take a full timed test every two weeks to track overall improvement."
        ),
    },
]

assert len(ARTICLES) == 20, f"Expected 20 articles, got {len(ARTICLES)}"


def make_record(article: dict, now_ms: int) -> dict:
    slug = slugify(article["title"])
    return {
        "slug": slug,
        "title": article["title"],
        "content": article["content"],
        "excerpt": article["excerpt"],
        "published": True,
        "ts": now_ms,
        "updated": now_ms,
    }


def main():
    parser = argparse.ArgumentParser(description="Seed 20 SEO blog articles to pielts RTDB.")
    parser.add_argument("--dry-run", action="store_true", help="Print slugs without writing to Firebase")
    parser.add_argument("--skip-existing", action="store_true", help="Skip articles whose slug already exists")
    args = parser.parse_args()

    # Init Firebase Admin
    cred = credentials.Certificate(SA_KEY_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

    blog_ref = db.reference("blog")

    if args.dry_run:
        print("DRY RUN — no writes will occur.\n")
        for a in ARTICLES:
            slug = slugify(a["title"])
            print(f"  {slug}")
        print(f"\nTotal: {len(ARTICLES)} articles")
        return

    # Fetch existing slugs
    existing = set()
    if args.skip_existing:
        snapshot = blog_ref.get(shallow=True) or {}
        existing = set(snapshot.keys())
        print(f"Found {len(existing)} existing articles.")

    now_ms = int(time.time() * 1000)
    written = 0
    skipped = 0

    for i, article in enumerate(ARTICLES, 1):
        record = make_record(article, now_ms - (i * 60_000))  # stagger ts by 1 min each
        slug = record["slug"]

        if slug in existing:
            print(f"  SKIP  [{i:02d}/20] {slug}")
            skipped += 1
            continue

        blog_ref.child(slug).set(record)
        print(f"  WRITE [{i:02d}/20] {slug}")
        written += 1

    print(f"\nDone. Written: {written}  Skipped: {skipped}")


if __name__ == "__main__":
    main()
