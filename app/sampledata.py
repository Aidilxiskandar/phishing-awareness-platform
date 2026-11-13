"""Generate realistic random staff for demos / testing.

Names lean Malaysian-mixed (Malay, Chinese, Indian) to fit the context, with a
spread of departments. Emails are derived from the name and de-duplicated.
"""
from __future__ import annotations

import random

FIRST_NAMES = [
    "Aisyah", "Haikal", "Nurul", "Faiz", "Syafiq", "Amir", "Hana", "Iman", "Zara",
    "Danish", "Aiman", "Farah", "Rizal", "Liyana", "Azlan", "Siti", "Adam", "Nadia",
    "Wei Jie", "Mei Ling", "Jia Hui", "Kai Wen", "Li Wei", "Xin Yi", "Jun Hao",
    "Hui Ying", "Zhe Kai", "Yee Ling", "Raj", "Priya", "Arjun", "Divya", "Karthik",
    "Anand", "Meena", "Suresh", "Kavya", "Vijay", "Deepa", "Sanjay", "Lina",
    "Farhan", "Izzah", "Daniel", "Grace", "Ethan", "Chloe", "Marcus", "Sarah",
]

LAST_NAMES = [
    "Abdullah", "Ismail", "Rahman", "Hassan", "Yusof", "Ibrahim", "Osman", "Karim",
    "Zainal", "Razak", "Tan", "Lim", "Lee", "Wong", "Ng", "Chong", "Goh", "Teoh",
    "Ong", "Chan", "Kumar", "Nair", "Pillai", "Raman", "Singh", "Menon", "Das",
    "Reddy", "Iyer", "Shah",
]

DEPARTMENTS = [
    "Finance", "Operations", "Information Technology", "Human Resources",
    "Marketing", "Legal", "Sales", "Customer Service", "Compliance",
    "Procurement", "Risk Management", "Internal Audit", "Corporate Affairs",
    "Administration",
]


def generate_staff(count: int, existing_emails: set[str] | None = None) -> list[dict]:
    """Return `count` dicts of {name, email, department, consented}."""
    existing = set(existing_emails or set())
    out: list[dict] = []
    for _ in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        base = f"{first}.{last}".lower().replace(" ", "")
        email = f"{base}@example.com"
        n = 2
        while email in existing:
            email = f"{base}{n}@example.com"
            n += 1
        existing.add(email)
        out.append({
            "name": name,
            "email": email,
            "department": random.choice(DEPARTMENTS),
            # Most staff have consented to drills; a few haven't yet.
            "consented": random.random() < 0.9,
        })
    return out
