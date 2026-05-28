# -----------------------------------------------------------
# app1/cli/patient_list.py
# -----------------------------------------------------------
# Standalone script to demonstrate FHIR Server access to
# retrieve and display a list of patient Resource records.
# -----------------------------------------------------------

# Standard library imports
import os
import json
from pathlib import Path
from typing import Any, Final

# Third-party imports
import requests
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv('APP_NAME')
FHIR_BASE_URL = os.getenv('FHIR_BASE_URL')


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

    print(f"🔥 {APP_NAME}\n")
    print("-" * 65)
    print("Patient Resource Summary")
    print("-" * 65)
    print(f" Resource Type: {resource_type}")
    print(f"   Resource ID: {resource_id}")
    print(f"Resource Total: {resource_total}")
    print(f" Link-Self URL: {resource_link_0.get("url")}")
    # print(f"Resource Count: {resource_count}")
    print("-" * 65)
    print()


def print_patient_list(patient_resource):
    # Get "entry": list
    patients = patient_resource.get("entry")

    if patients:
        pass  # there is at least one patient entry
    else:
        print("\nWarning, Will Robinson... there are no Patient Resource entries...\n")
        return

    print("┌", end='')
    print("─" * 82, end='')
    print("┐")
    print(f"│ Resource ID {' ' * 25}", end='')
    print(f"| Patient Name {' ' * 15}", end='')
    print(f"| Gender {' ' * 4} |")
    print("├", end='')
    print("─" * 82, end='')
    print("┤")

    for patient in patients:
        patient_id = patient.get("resource").get("id")
        patient_name_given  = patient.get("resource").get("name")[0].get("given")[0]
        patient_name_family = patient.get("resource").get("name")[0].get("family")
        patient_full_name = f"{patient_name_given} {patient_name_family}"
        patient_gender = patient.get("resource").get("gender")

        print("│ ", end='')
        print(f'{patient_id:<36}', end=' | ')
        print(f'{patient_full_name:<27} | ', end='')
        print(f'{patient_gender:<11} |')
    print("└", end='')
    print("─" * 82, end='')
    print("┘")
    print()


def main():
    """
    Fetch data via GET /Patients & return as Python dictionary
    Stop on failure or empty dictionary
    Display in JSON format to terminal & write results to file
    Display a summary of data returned
    Get a list of patient records from the Python dictionary
    Print list of patient records in nice format    
    """

    headers = {"Accept": "application/fhir+json"}

    patient_resource = fetch_patient_resource(FHIR_BASE_URL, headers)
    
    if patient_resource:
        print()
    else:
        return
    
    patient_resource_json = json.dumps(patient_resource, indent=2)
    # print(patient_resource_json, "\n")

    output_path = Path("./app1/data/patient.json")
    output_path.write_text(patient_resource_json + "\n", encoding="utf-8")
    
    print_patient_resource_summary(patient_resource)

    print_patient_list(patient_resource)


if __name__ == "__main__":
    main()