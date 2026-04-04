import re

def clean_text(text: str) -> str:
    """Removes weird characters and normalizes whitespace."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def calculate_overlap_percentage(source_words: set, target_words: set) -> int:
    """Calculates the percentage of target_words that exist in source_words."""
    if not target_words:
        return 0
    overlap = len(source_words.intersection(target_words))
    return int((overlap / len(target_words)) * 100)
