"""CBSE-style question paper blueprints, shared by the AI and offline engines."""

# (section, heading, marks_each, count, kind)
FULL_SECONDARY = [  # Classes 9-10: 80 marks, 3 hours (CBSE board pattern)
    ("A", "Multiple Choice Questions", 1, 20, "mcq"),
    ("B", "Very Short Answer Questions", 2, 6, "short"),
    ("C", "Short Answer Questions", 3, 7, "medium"),
    ("D", "Long Answer Questions", 5, 3, "long"),
    ("E", "Case / Source Based Questions", 4, 3, "case"),
]
FULL_MIDDLE = [  # Classes 6-8: 50 marks, 2 hours
    ("A", "Multiple Choice Questions", 1, 10, "mcq"),
    ("B", "Very Short Answer Questions", 2, 6, "short"),
    ("C", "Short Answer Questions", 3, 5, "medium"),
    ("D", "Long Answer Question", 5, 1, "long"),
    ("E", "Case Based Questions", 4, 2, "case"),
]
FULL_PRIMARY = [  # Classes 1-5: 25 marks, 1 hour
    ("A", "Choose the correct answer", 1, 10, "mcq"),
    ("B", "Answer in one or two lines", 2, 5, "short"),
    ("C", "Answer in detail", 5, 1, "long"),
]
CHAPTER_TEST = [  # any class: 20 marks, 45 minutes
    ("A", "Multiple Choice Questions", 1, 5, "mcq"),
    ("B", "Very Short Answer Questions", 2, 3, "short"),
    ("C", "Short Answer Questions", 3, 3, "medium"),
]


def blueprint(cls: int, paper_type: str) -> dict:
    if paper_type == "chapter":
        sections, time = CHAPTER_TEST, "45 minutes"
    elif cls >= 9:
        sections, time = FULL_SECONDARY, "3 hours"
    elif cls >= 6:
        sections, time = FULL_MIDDLE, "2 hours"
    else:
        sections, time = FULL_PRIMARY, "1 hour"
    total = sum(m * n for _, _, m, n, _ in sections)
    instructions = [
        f"This question paper contains {len(sections)} sections ({', '.join(s[0] for s in sections)}). All questions are compulsory.",
        *[f"Section {s} has {n} question{'s' if n > 1 else ''} of {m} mark{'s' if m > 1 else ''} each ({h.lower()})."
          for s, h, m, n, _ in sections],
        "Internal choice is provided in some questions. Attempt only one of the alternatives in such questions.",
        "Draw neat, labelled diagrams wherever necessary.",
    ]
    return {"sections": sections, "time": time, "max_marks": total, "instructions": instructions}
