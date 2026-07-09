# -----------------------------------------------------------
# app1/cli/patient_list.py
# -----------------------------------------------------------
# Standalone script to demonstrate FHIR Server access to
# retrieve and display a list of patient Resource records.
# -----------------------------------------------------------

"""
Run as a module from the project root folder:
python -m app1.cli.patient_list 
"""

# Standard library imports
import os
import json
from pathlib import Path
from typing import Any, Final

# Third-party imports
import requests
from dotenv import load_dotenv

# Project modules
from app1.cli.color import *
from app1.cli.helper import *

load_dotenv()

APP_NAME = os.getenv('APP_NAME')
FHIR_BASE_URL = os.getenv('FHIR_BASE_URL')
FHIR_API_TOKEN_EXTERNAL = os.getenv('FHIR_API_TOKEN_EXTERNAL_2')


def fetch_patient_resource(BASE_URL, headers) -> dict[str, Any] | None:
    # Get Patient resource bundle in JSON format & return as Python object
    try:
        response = requests.get(f"{BASE_URL}/Patient", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to  FHIR server at {BASE_URL}.")
        print(f"Is the HAPI FHIR server running?")
        return None
    except requests.exceptions.Timeout:
        print(f"Timed out connecting to FHIR server at {BASE_URL}.")
        return None
    except requests.exceptions.HTTPError as error:
        print(f"FHIR server returned an HTTP error: {error}")
        return None
    

def print_patient_resource_summary(patient_resource: dict[str, Any]) -> None:
    # Pull a few top-level fields out of the Patient resource dictionary
    # This is essentially "flattening" the object
    resource_type = patient_resource.get("resourceType", "Unknown")
    resource_id = patient_resource.get("id", "Unknown")
    resource_total = patient_resource.get("total", "Unknown")
    resource_link_0 = patient_resource.get("link")[0]
    # resource_count = len(patient_resource.get("entry"))

    print(f"🔥 {YELLOW}{APP_NAME} 🔥{RESET}\n")
    print(f"{'-' * 65}")
    print("Patient Resource Summary")
    print(f"-" * 65)
    print(f" Resource Type: {CYAN}{resource_type}{RESET}")
    print(f"   Resource ID: {CYAN}{resource_id}{RESET}")
    print(f"Resource Total: {CYAN}{resource_total}{RESET}")
    print(f" Link-Self URL: {CYAN}{CYAN}{resource_link_0.get("url")}{RESET}")
    # print(f"Resource Count: {resource_count}")
    print("-" * 65)
    print(RESET)


def print_patient_list(patients):
    # Get "entry": list

    print(f"┌", end='')
    print("─" * 112, end='')
    print("┐")
    print(f"│ Resource ID {' ' * 25}", end='')
    print(f"| Patient Name {' ' * 12}", end='')
    print(f"| Gender {' ' * 4}", end='')
    print(f"| Birth Date {' ' * 1}", end='')
    print(f"| Age ", end='')
    print(f"| Last Update |")
    print("├", end='')
    print("─" * 112, end='')
    print("┤")

    for patient in patients:
        patient_id = patient.get("resource").get("id")
        patient_name_given  = patient.get("resource").get("name")[0].get("given", [""])[0]
        patient_name_family = patient.get("resource").get("name")[0].get("family", "Unknown")
        patient_full_name = f"{patient_name_given} {patient_name_family}"
        patient_gender = patient.get("resource").get("gender")
        patient_birth_date = patient.get("resource").get("birthDate", "1200-01-01")
        patient_age = calculate_age(patient_birth_date)
        if patient_age == -1:
            patient_age = "--"
        last_updated = patient.get("resource").get("meta").get("lastUpdated")

        print("│ ", end='')
        print(f'{patient_id:<36}', end=' | ')
        print(f'{patient_full_name:<24} | ', end='')
        print(f'{patient_gender:<10} | ', end='')
        print(f'{patient_birth_date:<11} | ', end='')
        print(f'{patient_age:<3} | ', end='')
        print(f'{last_updated[:10]}  |')
    print("└", end='')
    print("─" * 112, end='')
    print("┘")
    print(RESET)


def main():
    """
    Fetch data; stop on failure or empty dictionary
    Display in JSON format to terminal & write results to file
    Display a summary of data returned
    Get a list of patient records from the Python dictionary
    Print list of patient records in nice format    
    """

    headers = {"Accept": "application/fhir+json"}

    if FHIR_API_TOKEN_EXTERNAL:
        headers["Authorization"] = f"Bearer {FHIR_API_TOKEN_EXTERNAL}"

    print(f"\n{headers}\n")

    patient_resource = fetch_patient_resource(FHIR_BASE_URL, headers)
    
    if patient_resource:
        pass
    else:
        return
    
    # Print to terminal stdout
    patient_resource_json = json.dumps(patient_resource, indent=2)
    print(patient_resource_json, "\n")

    # Write to file
    output_path = Path("./app1/data/patient.json")
    output_path.write_text(patient_resource_json + "\n", encoding="utf-8")
    
    print_patient_resource_summary(patient_resource)

    patients = patient_resource.get("entry")

    if patients:
        print_patient_list(patients)
    else:
        print("Danger, Will Robinson... there are no Patient Resource entries.\n")
        return


if __name__ == "__main__":
    main()