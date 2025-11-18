# laya-pdf-generator

Formats nice PDFs out of the data from Laya Healthcare consultants list:
https://www.layahealthcare.ie/hospitals/#/hospitals?planID=108&view=consultants

Usage
- Print available plans and specialities (no args): `python report.py`
- Generate for Dermatology on default plan: `python report.py --speciality DERM`
- Generate for a named plan and speciality: `python report.py -p "360 care select" -s Dermatology`
- Choose cover start date for plan list: `python report.py --cover-start 2025-11-18`

Notes
- The script fetches from Laya APIs:
  - `api/consultant/specialities.json`
  - `api/consultant/approved_hospitals.json`
  - `api/consultant/searchConsultants.json?countyId=&hospitalId=&specialityId=...`
  - `api/plans/plans/plansummary.json?coverStart=YYYY-MM-DD`
- If a parameter isn’t provided, the script prints available values for that parameter.

 Caching
 - Responses are cached under `.cache/` as JSON files.
 - Cache lifetime is 1 week; fresh cache is used to avoid re-fetching.
 - If the network fetch fails, a stale cache (if present) is used; otherwise optional local fallback files are read.
