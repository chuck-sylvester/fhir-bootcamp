# ---------------------------------------------------------------------
# app1/cli/helper.py
# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------

from datetime import date

def calculate_age(birth_date_str: str) -> int:
    """
    Calculates the age of a patient based on their FHIR birthDate string.
    Supports YYYY-MM-DD, YYYY-MM, and YYYY formats.
    """
    if not birth_date_str:
        raise ValueError("Birth date string cannot be empty.")
    
    today = date.today()
    
    # Split the FHIR date to check for partial dates
    parts = birth_date_str.split('-')
    year = int(parts[0])
    
    # Default to January 1st if month/day are missing
    month = int(parts[1]) if len(parts) > 1 else 1
    day   = int(parts[2]) if len(parts) > 2 else 1
    
    try:
        birth_date = date(year, month, day)
    except ValueError as e:
        raise ValueError(f"Invalid date format received: {birth_date_str}") from e

    # Calculate age
    age = today.year - birth_date.year
    
    # Adjust if the birthday hasn't occurred yet this year
    # (Checking the tuple (month, day) handles leap years smoothly)
    has_birthday_passed = (today.month, today.day) >= (birth_date.month, birth_date.day)
    if not has_birthday_passed:
        age -= 1
        
    if 0 <= age <= 125:
        return age
    else:
        return -1

# --- Quick Test Cases ---
# print(calculate_age("1995-05-15"))  # Standard FHIR date
# print(calculate_age("1995-11"))     # Partial date (defaults to Nov 1)
# print(calculate_age("1995"))        # Partial date (defaults to Jan 1)