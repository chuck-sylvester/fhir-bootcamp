# ---------------------------------------------------------------------
# app1/cli/observation_list.py
# ---------------------------------------------------------------------
# Retrieve and display Observation Resource data from FHIR Server
# ---------------------------------------------------------------------

"""
Run as a module from the project root folder:
python -m app1.cli.observation_list 
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


def fetch_observation_resource(BASE_URL, headers, params) -> dict[str, Any] | None:
    # Get Observation resource bundle in JSON format & return as Python object
    try:
        response = requests.get(f"{BASE_URL}/Observation", headers=headers, params=params, timeout=10)
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
    

def print_observation_resource_summary(observation_resource: dict[str, Any]) -> None:
    # Pull a few top-level fields out of the Observation resource dictionary
    # This is essentially "flattening" the object
    resource_type = observation_resource.get("resourceType", "Unknown")
    resource_id = observation_resource.get("id", "Unknown")
    resource_last_updated = f"{observation_resource.get("meta").get("lastUpdated")[:10]}"
    resource_link_url = observation_resource.get("link")[0].get("url")
    
    if observation_resource.get("entry"):
        resource_count = len(observation_resource.get("entry"))
    else:
        resource_count = 0

    print(f"🔥 {YELLOW}{APP_NAME} 🔥{RESET}\n")
    print(f"{'-' * 72}")
    print("Patient Resource Summary")
    print(f"-" * 72)
    print(f" Resource Type: {CYAN}{resource_type}{RESET}")
    print(f"   Resource ID: {CYAN}{resource_id}{RESET}")
    print(f"  Last Updated: {CYAN}{resource_last_updated}{RESET}")
    print(f"  Resource URL: {CYAN}{resource_link_url}{RESET}")
    print(f"Resource Count: {CYAN}{resource_count}{RESET}")

    # print(f"Resource Total: {CYAN}{resource_total}{RESET}")
    # print(f" Link-Self URL: {CYAN}{CYAN}{resource_link_0.get("url")}{RESET}")
    # print(f"Resource Count: {resource_count}")
    print("-" * 72)
    print(RESET)


def print_observation_list(observations):
    # Get "entry": list

    print(f"┌", end='')
    print("─" * 112, end='')
    print("┐")
    print(f"│ Resource ID {' ' * 20}", end='')
    print(f"| Resource Type {' ' * 9}", end='')
    print(f"| Status {' ' * 9}", end='')
    print(f"| Category {' ' * 9}", end='')
    print(f"| Last Update   |")
    print("├", end='')
    print("─" * 112, end='')
    print("┤")

    for observation in observations:
        observation_id = observation.get("resource").get("id")
        resource_type  = observation.get("resource").get("resourceType")
        observation_status = observation.get("resource").get("status")
        observation_category = observation.get("resource").get("category")[0].get("coding")[0].get("code")
        last_updated = observation.get("resource").get("meta").get("lastUpdated")

        print("│ ", end='')
        print(f'{observation_id:<31}', end=' | ')
        print(f'{resource_type:<22} | ', end='')
        print(f'{observation_status:<15} | ', end='')
        print(f'{observation_category:<17} | ', end='')
        print(f'{last_updated[:10]:<13} |')
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
    params =  {
        "patient": "4c05daee-cb43-41fd-927e-8763ca7ad966",
        "_count": 25
    }

    observation_resource = fetch_observation_resource(FHIR_BASE_URL, headers, params)
    
    if observation_resource:
        pass
    else:
        return
    
    # Print to terminal stdout
    observation_resource_json = json.dumps(observation_resource, indent=2)
    print(observation_resource_json, "\n")

    # Write to file
    output_path = Path("./app1/data/observation.json")
    output_path.write_text(observation_resource_json + "\n", encoding="utf-8")
    
    print_observation_resource_summary(observation_resource)

    observations = observation_resource.get("entry")

    if observations:
        print_observation_list(observations)
    else:
        print("Danger, Will Robinson... there are no Observation Resource entries.\n")
        return


if __name__ == "__main__":
    main()