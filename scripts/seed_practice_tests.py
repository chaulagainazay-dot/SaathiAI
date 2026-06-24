#!/usr/bin/env python3
"""Seed 5 writing + 5 speaking practice tests to Firebase RTDB at public/tests/{type}/{id}."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import firebase_admin
from firebase_admin import credentials, db


def _init_firebase():
    cred_paths = [
        ROOT / "firebase-admin.json",
        ROOT / "data" / "firebase-admin.json",
        ROOT / "data" / "serviceAccount.json",
        ROOT / "data" / "firebase-service-account.json",
        ROOT / "scripts" / "pielts-sa-key.json",
    ]
    cred_path = next((p for p in cred_paths if p.exists()), None)
    if not cred_path:
        print(f"ERROR: No firebase credentials found. Tried: {[str(p) for p in cred_paths]}")
        sys.exit(1)

    db_url = os.getenv("FIREBASE_DATABASE_URL", "https://ielts-and-language-practice-default-rtdb.firebaseio.com")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(cred_path)), {"databaseURL": db_url})
    print(f"  Firebase initialised: {cred_path.name} → {db_url}")
    return db.reference("/")


WRITING_TESTS = [
    {
        "id": "wt1", "title": "Technology & Society", "difficulty": "intermediate",
        "task1": {"prompt": "The graph below shows the percentage of households with internet access in four countries from 2010 to 2020.", "type": "line_graph", "timeMinutes": 20, "minWords": 150},
        "task2": {"prompt": "Technology has made it easier for people to connect with others, but has also made society more isolated. To what extent do you agree or disagree?", "type": "opinion", "timeMinutes": 40, "minWords": 250},
    },
    {
        "id": "wt2", "title": "Education & Learning", "difficulty": "intermediate",
        "task1": {"prompt": "The bar chart below shows the number of students choosing different subjects at a university in 2015 and 2023.", "type": "bar_chart", "timeMinutes": 20, "minWords": 150},
        "task2": {"prompt": "Some people believe that university education should be free for all students. Others think students should pay tuition fees. Discuss both views and give your own opinion.", "type": "discuss_both", "timeMinutes": 40, "minWords": 250},
    },
    {
        "id": "wt3", "title": "Environment & Climate", "difficulty": "upper-intermediate",
        "task1": {"prompt": "The diagram below shows how solar panels work to produce electricity for a home.", "type": "process_diagram", "timeMinutes": 20, "minWords": 150},
        "task2": {"prompt": "Climate change is the most serious problem facing humanity today. The only solution is for individuals to change their behaviour. To what extent do you agree or disagree?", "type": "opinion", "timeMinutes": 40, "minWords": 250},
    },
    {
        "id": "wt4", "title": "Work & Career", "difficulty": "upper-intermediate",
        "task1": {"prompt": "The pie charts below show the percentage of time spent on different activities by office workers in 2010 and 2022.", "type": "pie_chart", "timeMinutes": 20, "minWords": 150},
        "task2": {"prompt": "Many people choose to work from home rather than in an office. What are the advantages and disadvantages of working from home?", "type": "advantages_disadvantages", "timeMinutes": 40, "minWords": 250},
    },
    {
        "id": "wt5", "title": "Society & Culture", "difficulty": "advanced",
        "task1": {"prompt": "The table below shows data about museum visitors in five countries in 2022.", "type": "table", "timeMinutes": 20, "minWords": 150},
        "task2": {"prompt": "In many countries, traditional cultures and customs are disappearing due to globalisation. Discuss both views and give your opinion.", "type": "discuss_both", "timeMinutes": 40, "minWords": 250},
    },
]

SPEAKING_TESTS = [
    {
        "id": "st1", "title": "Hometown & Travel", "difficulty": "intermediate",
        "part1": ["Where are you from originally?", "What do you like most about your hometown?", "Has your hometown changed a lot in recent years?"],
        "part2": {"cueCard": "Describe a journey or trip you have taken that you particularly enjoyed.", "points": ["Where you went", "Who you went with", "What you did there", "Explain why you enjoyed it"], "prepTime": 60, "speakTime": 120},
        "part3": ["What are the most popular types of tourism in your country?", "How has the travel industry changed due to technology?", "Do you think tourism has more positive or negative effects on local communities?"],
    },
    {
        "id": "st2", "title": "Technology & Daily Life", "difficulty": "intermediate",
        "part1": ["How often do you use a smartphone?", "Do you think you spend too much time on your phone?", "How has technology changed the way you study?"],
        "part2": {"cueCard": "Describe a piece of technology that you find very useful.", "points": ["What it is", "How you use it", "How long you have had it", "Explain why you find it useful"], "prepTime": 60, "speakTime": 120},
        "part3": ["Do older generations have difficulties adapting to new technologies?", "What are the risks of relying too much on technology?", "How might technology change education in the next 20 years?"],
    },
    {
        "id": "st3", "title": "Education & Learning", "difficulty": "upper-intermediate",
        "part1": ["Do you prefer studying alone or with others?", "What was your favourite subject at school?", "Are you currently studying anything new?"],
        "part2": {"cueCard": "Describe a teacher who had a great influence on you.", "points": ["Who the teacher was", "What subject they taught", "What made them special", "Explain how they influenced you"], "prepTime": 60, "speakTime": 120},
        "part3": ["What qualities make a great teacher?", "How important is it for children to learn a second language?", "Does the education system in your country prepare young people well for the future?"],
    },
    {
        "id": "st4", "title": "Environment & Nature", "difficulty": "upper-intermediate",
        "part1": ["How often do you spend time in nature?", "Do people in your country care about the environment?", "What do you do to help protect the environment?"],
        "part2": {"cueCard": "Describe a place in nature that you have visited and enjoyed.", "points": ["Where the place was", "When you went there", "What you did there", "Explain why you enjoyed it"], "prepTime": 60, "speakTime": 120},
        "part3": ["What are the main environmental problems facing your country?", "Who should be responsible for protecting the environment?", "How might climate change affect daily life in the future?"],
    },
    {
        "id": "st5", "title": "Work & Ambitions", "difficulty": "advanced",
        "part1": ["What kind of work do you do or would you like to do?", "What do you enjoy most about your work or studies?", "Is it important to have a job you enjoy?"],
        "part2": {"cueCard": "Describe an ambitious goal you have for the future.", "points": ["What the goal is", "When you decided on this goal", "What steps you are taking", "Explain why it is important to you"], "prepTime": 60, "speakTime": 120},
        "part3": ["How important is financial success compared to job satisfaction?", "Do young people today have different career expectations than previous generations?", "What role should governments play in helping people find employment?"],
    },
]


def main():
    print("Seeding practice tests to Firebase RTDB...")
    root_ref = _init_firebase()

    writing_ref = root_ref.child("public/tests/writing")
    for t in WRITING_TESTS:
        writing_ref.child(t["id"]).set(t)
        print(f"  Writing: {t['id']} - {t['title']}")

    speaking_ref = root_ref.child("public/tests/speaking")
    for t in SPEAKING_TESTS:
        speaking_ref.child(t["id"]).set(t)
        print(f"  Speaking: {t['id']} - {t['title']}")

    root_ref.child("public/tests/_meta").set({
        "seeded": True, "version": "1.0.0",
        "types": ["writing", "speaking"],
        "counts": {"writing": 5, "speaking": 5},
    })
    print("  Meta node written")
    print("Done! Tests available at public/tests/ in RTDB.")


if __name__ == "__main__":
    main()
