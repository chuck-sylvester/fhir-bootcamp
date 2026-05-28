# fhir-bootcamp
Companion repository for Medblocks 10-week FHIR bootcamp

## Overview

This repository is used to build the five FHIR applications covered in the Medblocks 10-week bootcamp. I will also document the approach and specific development tasks performed to establish a local macOS development environment, build each of the five sample applications, test each application locally, and deploy each app to an external hosting service. The target hosting service will be Oracle Cloud Infrastructure (OCI).

The applications presented and developed by the bootcamp instructor use vite and Svelte. I hve nothing against the JavaScript / TypeScript framework aproach , but prefer a Python-based technology stack that is primarily Server-Side Rendered (SSR).

I will be designing and developing each of the applications myself with zero or very limited AI assistance to write the code. I will use Claude to help me document the step-by-step work performed to build each application, including local environment setup, the tech stack, installing and using dependencies, how to run each app locally, and (later) how to deploy and run each app within an external hosting environment.

This documentation will be captured in five markdown docuements -- one for each app -- to be located in the docs/ directory. The objective for capturing the detailed implementation is to document this for future developers and my future self. It may also be used to create a video that documents the implementation approach and code for each of the five apps. I will collaborate with Claude to create and update the documents.

So far, only an new and empty git / GitHub repository has been created, along with an initial .gitignore file and this initial README.md. The project folder structure will be defined as each application is designed and developed, but my strategy and design decision is to create a new and separate top-level folder for each application, for example: fhir-bootcamp/app1, fhir-bootcamp/app2, etc. To reenforce learning, each project will be built from scratch, from the ground up. The only shared item may be a root-level requirements.txt file, a root-level .env file, and a root-level config.py file. I will also create a root-level, project-wide Python environment, called .venv.

Note to Claude: as an initial task, please review this overview of the project and provide any initial feedback or questions that will help with your feedback. Do not make any file, folder, or code changes. After I review your initial feedback, the first items that I will create will be the app1/ project folder and the first developer guide in the docs/ directory.

