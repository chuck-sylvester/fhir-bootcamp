# app3 - Cerner SMART Practitioner App

## Requirements

Build using a Web Application and the Cerner SMART on FHIR Sandbox:

1. Initiate the launch automatically when opened
2. Display a Patient Banner (or not) depending on what the EHR instructs via token context.
3. List all of the current patient’s vital signs.
4. Allow the user to create new vital sign entries.

## EHR Launch Info

Read the SMART EHR Launch Flow specification  
[SMART EHR Launch](https://build.fhir.org/ig/HL7/smart-app-launch/app-launch.html#launch-app-ehr-launch)  

Register a Practitioner App on Cerner’s Sandbox
[Cerner Code Sandbox](https://code-console.cerner.com/)  

Two Ways to Render an App  
 - iFrame
 - Popup

 Three key components to know about:  
  - Launch URL
  - `iss` parameter
  - `launch` parameter