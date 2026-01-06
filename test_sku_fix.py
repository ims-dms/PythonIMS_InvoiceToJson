"""
Test script to verify SKU vs sku_code classification fix
Tests that codes like "1212-MM" are moved to sku field when sku is empty
"""
import re


def _norm_str(v):
    try:
        return str(v).strip()
    except Exception:
        return ""


def _is_hscode_like(v: str) -> bool:
    s = _norm_str(v)
    # HS codes are typically 4-8+ digits, with only digits (sometimes with dots)
    return bool(re.fullmatch(r"\d{4,10}(?:[.\-]\d{1,4})?", s))


def test_sku_code_fix():
    """Test the SKU/sku_code/hscode disambiguation logic"""
    
    # Test Case 1: HSCode in sku should move to hscode, then sku_code should move to sku
    print("=" * 80)
    print("Test Case 1: HSCode in sku field should move to hscode, sku_code to sku")
    print("=" * 80)
    
    sku_list = ["100830", "100830", "100830"]
    sku_code_list = ["1212-MM", "1212-44", "Conditioner"]
    hscode_list = ["", "", ""]
    
    # Apply the enhanced fix logic
    max_items = max(len(sku_list), len(sku_code_list), len(hscode_list))
    for i in range(max_items):
        sku_val = _norm_str(sku_list[i]) if i < len(sku_list) else ""
        sku_code_val = _norm_str(sku_code_list[i]) if i < len(sku_code_list) else ""
        hs_val = _norm_str(hscode_list[i]) if i < len(hscode_list) else ""
        
        # If sku contains an HS code (purely numeric), move it to hscode
        if sku_val and _is_hscode_like(sku_val):
            # Move to hscode if hscode is empty
            if not hs_val:
                if i < len(hscode_list):
                    hscode_list[i] = sku_val
                else:
                    hscode_list.append(sku_val)
            # Clear the sku
            if i < len(sku_list):
                sku_list[i] = ""
            sku_val = ""  # Update for next check
        
        # If sku is now empty but sku_code exists and is not an HS code, move sku_code to sku
        if not sku_val and sku_code_val and not _is_hscode_like(sku_code_val):
            # Move sku_code to sku
            if i < len(sku_list):
                sku_list[i] = sku_code_val
            else:
                sku_list.append(sku_code_val)
            # Clear the sku_code
            if i < len(sku_code_list):
                sku_code_list[i] = ""
    
    print(f"After fix:")
    for i in range(max_items):
        sku = sku_list[i] if i < len(sku_list) else ""
        sku_code = sku_code_list[i] if i < len(sku_code_list) else ""
        hscode = hscode_list[i] if i < len(hscode_list) else ""
        print(f"  Item {i+1}: sku='{sku}', sku_code='{sku_code}', hscode='{hscode}'")
    
    # Verify results
    assert sku_list[0] == "1212-MM", "1212-MM should be in sku"
    assert sku_list[1] == "1212-44", "1212-44 should be in sku"
    assert sku_list[2] == "Conditioner", "Conditioner should be in sku"
    assert sku_code_list[0] == "", "sku_code should be empty"
    assert sku_code_list[1] == "", "sku_code should be empty"
    assert sku_code_list[2] == "", "sku_code should be empty"
    assert hscode_list[0] == "100830", "100830 should be in hscode"
    assert hscode_list[1] == "100830", "100830 should be in hscode"
    assert hscode_list[2] == "100830", "100830 should be in hscode"
    print("✓ Test Case 1 PASSED\n")
    
    # Test Case 2: Product codes in sku_code should move to sku when sku is empty
    print("=" * 80)
    print("Test Case 2: Product codes in sku_code should move to sku when sku is empty")
    print("=" * 80)
    
    sku_list = ["", "", ""]
    sku_code_list = ["1212-MM", "1212-44", "ABC-123"]
    hscode_list = ["100830", "100830", "100830"]
    
    # Apply the enhanced fix logic
    max_items = max(len(sku_list), len(sku_code_list), len(hscode_list))
    for i in range(max_items):
        sku_val = _norm_str(sku_list[i]) if i < len(sku_list) else ""
        sku_code_val = _norm_str(sku_code_list[i]) if i < len(sku_code_list) else ""
        hs_val = _norm_str(hscode_list[i]) if i < len(hscode_list) else ""
        
        # If sku contains an HS code (purely numeric), move it to hscode
        if sku_val and _is_hscode_like(sku_val):
            if not hs_val:
                if i < len(hscode_list):
                    hscode_list[i] = sku_val
                else:
                    hscode_list.append(sku_val)
            if i < len(sku_list):
                sku_list[i] = ""
            sku_val = ""
        
        # If sku is now empty but sku_code exists and is not an HS code, move sku_code to sku
        if not sku_val and sku_code_val and not _is_hscode_like(sku_code_val):
            if i < len(sku_list):
                sku_list[i] = sku_code_val
            else:
                sku_list.append(sku_code_val)
            if i < len(sku_code_list):
                sku_code_list[i] = ""
    
    print(f"After fix:")
    for i in range(max_items):
        sku = sku_list[i] if i < len(sku_list) else ""
        sku_code = sku_code_list[i] if i < len(sku_code_list) else ""
        hscode = hscode_list[i] if i < len(hscode_list) else ""
        print(f"  Item {i+1}: sku='{sku}', sku_code='{sku_code}', hscode='{hscode}'")
    
    # Verify results
    assert sku_list[0] == "1212-MM", "1212-MM should be in sku"
    assert sku_list[1] == "1212-44", "1212-44 should be in sku"
    assert sku_list[2] == "ABC-123", "ABC-123 should be in sku"
    assert sku_code_list[0] == "", "sku_code should be empty"
    assert sku_code_list[1] == "", "sku_code should be empty"
    assert sku_code_list[2] == "", "sku_code should be empty"
    print("✓ Test Case 2 PASSED\n")
    
    # Test Case 3: Numeric HS codes in sku_code should NOT move to sku
    print("=" * 80)
    print("Test Case 3: Numeric HS codes in sku_code should stay in sku_code")
    print("=" * 80)
    
    sku_list = ["", ""]
    sku_code_list = ["100830", "1234567"]
    hscode_list = []
    
    # Apply the enhanced fix logic
    max_items = max(len(sku_list), len(sku_code_list), len(hscode_list) if hscode_list else 0)
    for i in range(max_items):
        sku_val = _norm_str(sku_list[i]) if i < len(sku_list) else ""
        sku_code_val = _norm_str(sku_code_list[i]) if i < len(sku_code_list) else ""
        hs_val = _norm_str(hscode_list[i]) if hscode_list and i < len(hscode_list) else ""
        
        # If sku contains an HS code (purely numeric), move it to hscode
        if sku_val and _is_hscode_like(sku_val):
            if not hs_val:
                if hscode_list and i < len(hscode_list):
                    hscode_list[i] = sku_val
                else:
                    hscode_list.append(sku_val)
            if i < len(sku_list):
                sku_list[i] = ""
            sku_val = ""
        
        # If sku is now empty but sku_code exists and is not an HS code, move sku_code to sku
        if not sku_val and sku_code_val and not _is_hscode_like(sku_code_val):
            if i < len(sku_list):
                sku_list[i] = sku_code_val
            else:
                sku_list.append(sku_code_val)
            if i < len(sku_code_list):
                sku_code_list[i] = ""
    
    print(f"After fix:")
    for i in range(max_items):
        sku = sku_list[i] if i < len(sku_list) else ""
        sku_code = sku_code_list[i] if i < len(sku_code_list) else ""
        print(f"  Item {i+1}: sku='{sku}', sku_code='{sku_code}'")
    
    # Verify results - numeric codes should stay in sku_code
    assert sku_list[0] == "", "sku should be empty when sku_code is numeric"
    assert sku_list[1] == "", "sku should be empty when sku_code is numeric"
    assert sku_code_list[0] == "100830", "Numeric HS code should stay in sku_code"
    assert sku_code_list[1] == "1234567", "Numeric HS code should stay in sku_code"
    print("✓ Test Case 3 PASSED\n")
    
    # Test Case 4: When sku is not empty with actual description, nothing should change
    print("=" * 80)
    print("Test Case 4: When sku has actual product description, nothing should change")
    print("=" * 80)
    
    sku_list = ["Product Name", "Another Product"]
    sku_code_list = ["1212-MM", "ABC-123"]
    hscode_list = ["100830", "100830"]
    
    # Apply the enhanced fix logic
    max_items = max(len(sku_list), len(sku_code_list), len(hscode_list))
    for i in range(max_items):
        sku_val = _norm_str(sku_list[i]) if i < len(sku_list) else ""
        sku_code_val = _norm_str(sku_code_list[i]) if i < len(sku_code_list) else ""
        hs_val = _norm_str(hscode_list[i]) if i < len(hscode_list) else ""
        
        # If sku contains an HS code (purely numeric), move it to hscode
        if sku_val and _is_hscode_like(sku_val):
            if not hs_val:
                if i < len(hscode_list):
                    hscode_list[i] = sku_val
                else:
                    hscode_list.append(sku_val)
            if i < len(sku_list):
                sku_list[i] = ""
            sku_val = ""
        
        # If sku is now empty but sku_code exists and is not an HS code, move sku_code to sku
        if not sku_val and sku_code_val and not _is_hscode_like(sku_code_val):
            if i < len(sku_list):
                sku_list[i] = sku_code_val
            else:
                sku_list.append(sku_code_val)
            if i < len(sku_code_list):
                sku_code_list[i] = ""
    
    print(f"After fix:")
    for i in range(max_items):
        sku = sku_list[i] if i < len(sku_list) else ""
        sku_code = sku_code_list[i] if i < len(sku_code_list) else ""
        hscode = hscode_list[i] if i < len(hscode_list) else ""
        print(f"  Item {i+1}: sku='{sku}', sku_code='{sku_code}', hscode='{hscode}'")
    
    # Verify results - sku should remain unchanged
    assert sku_list[0] == "Product Name", "sku should not be overwritten"
    assert sku_list[1] == "Another Product", "sku should not be overwritten"
    assert sku_code_list[0] == "1212-MM", "sku_code should stay as is"
    assert sku_code_list[1] == "ABC-123", "sku_code should stay as is"
    print("✓ Test Case 4 PASSED\n")
    
    print("=" * 80)
    print("✓ ALL TESTS PASSED!")
    print("=" * 80)


if __name__ == "__main__":
    test_sku_code_fix()
