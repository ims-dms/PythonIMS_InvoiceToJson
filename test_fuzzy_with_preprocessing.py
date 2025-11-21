"""
Test fuzzy matching with preprocessing
"""

from rapidfuzz import fuzz
import re

def preprocess(text):
    """Clean and normalize text for matching"""
    # Convert to uppercase
    text = text.upper()
    # Remove special characters except spaces
    text = re.sub(r'[^A-Z0-9\s]', ' ', text)
    # Remove extra spaces
    text = ' '.join(text.split())
    return text

# OCR string
ocr_raw = "Kingfisher Strong -Bottle 330ml"
ocr = preprocess(ocr_raw)

# Database strings
db_strings = [
    "KINGFISHER STRONG PREMIUM BEER 330 ML",
    "KINGFISHER STRONG BEER 330ML BOTTLE MRP-145",
    "KINGFISHER STRONG BEER 330ML BOTTLE MRP-160",
    "KINGFISHER STRONG BEER 650ML BOTTLE MRP-265",
    "KINGFISHER STRONG BEER CAN 500ML MRP-230",
]

print(f"OCR Raw: '{ocr_raw}'")
print(f"OCR Preprocessed: '{ocr}'")
print("="*80)

for db_str_raw in db_strings:
    db_str = preprocess(db_str_raw)
    
    scores = {
        'ratio': fuzz.ratio(ocr, db_str),
        'partial_ratio': fuzz.partial_ratio(ocr, db_str),
        'token_sort_ratio': fuzz.token_sort_ratio(ocr, db_str),
        'token_set_ratio': fuzz.token_set_ratio(ocr, db_str),
        'WRatio': fuzz.WRatio(ocr, db_str),
    }
    
    print(f"\nDB String Raw: '{db_str_raw}'")
    print(f"DB String Preprocessed: '{db_str}'")
    for scorer_name, score in scores.items():
        print(f"  {scorer_name:20s}: {score:.2f}")
    print(f"  Best score: {max(scores.values()):.2f}")
