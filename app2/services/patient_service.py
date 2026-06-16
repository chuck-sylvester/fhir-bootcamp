# -----------------------------------------------------------
# app/services/patient_service.py
# -----------------------------------------------------------

import requests
from app2.config import settings
import xml.etree.ElementTree as ET


def get_patient():
    """Get patient resource data."""
    base_url = settings.epic_fhir_base_url

    headers = {"Accept": "application/fhir+json"}

    output = requests.get(f"{base_url}/Patient", headers=headers)
    
    print(output.json())
    
    return output.json()
