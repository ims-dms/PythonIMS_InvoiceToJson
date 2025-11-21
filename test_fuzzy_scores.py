"""
Test fuzzy matching between OCR and database strings
"""

from rapidfuzz import fuzz

# OCR string
ocr = "Kingfisher Strong -Bottle 330ml"

# Database strings
db_strings = [
    "KINGFISHER STRONG PREMIUM BEER 330 ML",
    "KINGFISHER STRONG BEER 330ML BOTTLE MRP-145",
    "KINGFISHER STRONG BEER 330ML BOTTLE MRP-160",
    "KINGFISHER STRONG BEER 650ML BOTTLE MRP-265",
    "KINGFISHER STRONG BEER CAN 500ML MRP-230",
]

print(f"OCR String: '{ocr}'")
print("="*80)

for db_str in db_strings:
    scores = {
        'ratio': fuzz.ratio(ocr, db_str),
        'partial_ratio': fuzz.partial_ratio(ocr, db_str),
        'token_sort_ratio': fuzz.token_sort_ratio(ocr, db_str),
        'token_set_ratio': fuzz.token_set_ratio(ocr, db_str),
        'WRatio': fuzz.WRatio(ocr, db_str),
    }
    
    print(f"\nDB String: '{db_str}'")
    for scorer_name, score in scores.items():
        print(f"  {scorer_name:20s}: {score:.2f}")
    print(f"  Best score: {max(scores.values()):.2f}")
