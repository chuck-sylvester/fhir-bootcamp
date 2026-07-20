# ---------------------------------------------------------------------
# app1/cli/capability_statement.py
# ---------------------------------------------------------------------
# Retrieve and display CapabilityStatement resource
# ---------------------------------------------------------------------

"""
Run as a module from the project root folder:
python -m app1.cli.capability_statement
"""

# Standard library imports
import os
import json
from pathlib import Path
from typing import Any, Final

# Third-pary imports
import requests
from dotenv import load_dotenv

# Project modules
from app1.cli.color import *
from app1.cli.helper import *

load_dotenv()

APP_NAME = os.getenv('APP_NAME')
FHIR_BASE_URL = os.getenv('FHIR_BASE_URL')


def fetch_capability_statement_resource(base_url, headers) -> dict[str, Any] | None:
    """Get CapabilityStatement resource from FHIR server & return as a Python object."""
    try:
        response = requests.get(f"{base_url}/metadata", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to FHIR server at {base_url}")
        print(f"Is the HAPI FHIR server running?")
        return None
    except requests.exceptions.Timeout:
        print(f"Timed out connecting to FHIR server at {base_url}")
        return None
    except requests.exceptions.HTTPError as error:
        print(f"FHIR server returned an HTTP error: {error}")
        return None


def print_capability_statement_resource_summary(resource: dict[str, Any]) -> None:
    # Pull a few top-level fields out of the resource dictionary
    # This is essentially "flattening out" the data structure
    resource_type = resource.get("resourceType", "Unknown")
    resource_id = resource.get("id", "Unknown")
    resource_name = resource.get("software").get("name")
    resource_version = resource.get("software").get("version")
    resource_url = resource.get("implementation").get("url")
    resource_count = len(resource.get('rest')[0].get('resource'))

    print(f"🔥 {YELLOW}{APP_NAME} 🔥{RESET}\n")
    print("-" * 65)
    print("CapabilityStatement Resource Summary")
    print("-" * 65)
    print(f"      resource.resourceType: {YELLOW}{resource_type}{RESET}")
    print(f"                resource.id: {YELLOW}{resource_id}{RESET}")
    print(f"     resource.software.name: {YELLOW}{resource_name}{RESET}")
    print(f"  resource.software.version: {YELLOW}{resource_version}{RESET}")
    print(f"resource.implementation.url: {YELLOW}{resource_url}{RESET}")
    print(f"             Resource Count: {CYAN}{resource_count}{RESET}")
    print("-" * 65)

def get_resource_type_list(resource_list: list[dict]) -> list[str]:
    resource_type_list = []

    for resource in resource_list:
        resource_type = resource.get("type")
        if resource_type:
            resource_type_list.append(resource_type)

    return resource_type_list


def main():
    """
    Fetch resource data; stop on failure or empty dictionary
    Display in JSON format to terminal & write to file
    Display summary of data returned
    Get and print list of capabilities from Python dictionary
    """

    headers = {"Accept": "application/fhir+json"}

    capability_statement_resource = fetch_capability_statement_resource(FHIR_BASE_URL, headers)

    if capability_statement_resource:
        pass
    else:
        return

    # Print CapabilityStatement JSON to stdout
    capability_statement_resource_json = json.dumps(capability_statement_resource, indent=2)
    print(capability_statement_resource_json, "\n")

    # Write to file
    output_path = Path("./app1/data/capability_statement.json")
    output_path.write_text(capability_statement_resource_json + "\n", encoding="utf-8")

    print_capability_statement_resource_summary(capability_statement_resource)

    resource_list = capability_statement_resource.get('rest')[0].get('resource')

    resource_type_list = get_resource_type_list(resource_list)
    
    for idx, resource in enumerate(resource_type_list, 1):
        if (idx) % 3 == 0:
            print(resource)
        else:
            print(f"{resource:<35}", end='')

    print(f"\n\n{YELLOW}Resource Type Count: {CYAN}{idx}{RESET}\n")


if __name__ == "__main__":
    main()