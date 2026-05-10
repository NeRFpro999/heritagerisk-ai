# HeritageRisk AI

HeritageRisk AI is a citizen-powered computer vision platform for early detection and response to heritage-site deterioration.

Users submit guided smartphone photos of heritage places. The system checks image quality, detects visible damage such as cracks, graffiti, staining, erosion, and vegetation growth, compares observations over time, calculates a risk score, and creates a verified conservation case.

After human review, the case can be routed to the responsible site owner, local council, heritage authority, or cultural heritage process.

## Mission

HeritageRisk AI turns public photos into conservation action.

## Problem

Many heritage sites deteriorate slowly through cracks, erosion, water damage, vegetation growth, vandalism, fire, flooding, pollution, and neglect. These changes are often noticed too late because many sites cannot be inspected frequently.

At the same time, ordinary people walk past these places every day with smartphones.

HeritageRisk AI explores whether citizen smartphone imagery and AI can become a scalable early-warning layer for heritage conservation.

## Core Workflow

1. A user selects or adds a heritage site.
2. The app guides the user to upload useful photos.
3. The system checks image quality and metadata.
4. AI detects visible damage.
5. The app compares new observations with older images.
6. A risk score is calculated.
7. A human reviewer verifies the case.
8. The case is routed to the responsible organisation or site manager.
9. The response/action status is tracked.

## Initial MVP

The first version will focus on:

- Uploading a heritage-site image
- Creating a site observation
- Detecting or manually marking visible damage
- Creating a risk case
- Generating a basic evidence report
- Tracking the case status

## Tech Stack

Planned stack:

- Backend: FastAPI
- Database: SQLite first, PostgreSQL later
- AI/Image Processing: OpenCV and PyTorch later
- Frontend: React later
- Reports: Markdown first, PDF later
- Storage: Local uploads first, cloud storage later

## Project Status

Currently in early MVP development.