# VS Code: FHIR R4 JSON Schema Validation

This guide documents how to configure VS Code to validate FHIR R4 resource JSON files using the official HL7 FHIR R4 JSON schema. This setup applies project-wide and benefits all apps (`app1/`, `app2/`, etc.).

---

## Overview

VS Code's built-in JSON language support can validate any JSON file against a JSON Schema, providing:

- Inline validation errors (red underlines) for invalid FHIR structure
- IntelliSense / autocomplete for FHIR resource properties
- Hover documentation for recognized fields

The configuration lives in `.vscode/settings.json` and targets files by glob pattern, so you control exactly which JSON files are validated as FHIR resources.

---

## Step 1: Download the FHIR R4 JSON Schema

The official schema is published by HL7 and is approximately 20 MB uncompressed.

1. Download the zip from the HL7 FHIR R4 specification:

   ```
   https://hl7.org/fhir/R4/fhir.schema.json.zip
   ```

2. Unzip the archive. It produces a single file: `fhir.schema.json`.

3. Place the file at the following path in this project:

   ```
   .vscode/schemas/fhir.schema.json
   ```

   Create the `.vscode/schemas/` directory if it does not exist:

   ```bash
   mkdir -p .vscode/schemas
   ```

---

## Step 2: Gitignore the Schema File

The schema file is large (~20 MB) and is freely available from HL7, so it should not be committed to the repository. Add it to `.gitignore`:

```
# FHIR R4 JSON schema (downloaded separately — see docs/vscode-fhir-schema.md)
.vscode/schemas/
```

---

## Step 3: Configure VS Code Schema Association

Create or update `.vscode/settings.json` with a `json.schemas` entry. The `fileMatch` glob patterns determine which JSON files are validated against the FHIR R4 schema.

```json
{
  "json.schemas": [
    {
      "fileMatch": ["app*/**/*.fhir.json"],
      "url": "./.vscode/schemas/fhir.schema.json"
    }
  ]
}
```

**What this does:**
- Applies to any file matching `app*/**/*.fhir.json` — i.e., any `.fhir.json` file anywhere inside `app1/`, `app2/`, etc.
- Uses the local schema file rather than fetching it remotely on every open.

**File naming convention:**  
Name your FHIR resource JSON files with the `.fhir.json` extension (e.g., `patient_sample.fhir.json`) to distinguish them from other JSON files (config, fixtures, etc.) that should not be validated as FHIR resources.

---

## Verification

1. Open any `.fhir.json` file in the project.
2. Look for the schema indicator in the VS Code status bar (bottom right). It should show the schema name or path.
3. Introduce a deliberate error (e.g., set `"resourceType": "Bogus"`) and confirm that VS Code underlines it in red.
4. Remove the error, then use `Ctrl+Space` inside a resource object to confirm that autocomplete suggestions appear.

---

## Re-downloading the Schema

If the schema file is missing (e.g., after a fresh clone), repeat Step 1. The download URL and destination path are fixed; no other configuration changes are needed.

---

## Reference

- HL7 FHIR R4 specification downloads: `https://hl7.org/fhir/R4/downloads.html`
- VS Code JSON schema documentation: `https://code.visualstudio.com/docs/languages/json#_json-schemas-and-settings`
