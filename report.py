#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from xml.sax.saxutils import escape as xml_escape


BASE = "https://www.layahealthcare.ie/api"
URL_SPECIALITIES = f"{BASE}/consultant/specialities.json"
URL_HOSPITALS = f"{BASE}/consultant/approved_hospitals.json"
URL_CONSULTANTS = f"{BASE}/consultant/searchConsultants.json"
URL_PLANSUMMARY = f"{BASE}/plans/plans/plansummary.json"

CACHE_DIR = ".cache"
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 1 week


def http_get_json(url: str, params: dict | None = None, timeout: int = 30):
    if params:
        qs = urllib.parse.urlencode(params)
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "laya-pdf/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        data = resp.read().decode(charset)
        return json.loads(data)


def ensure_cache_dir():
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception:
        pass


def cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)


def load_cache_if_fresh(name: str, max_age_seconds: int = CACHE_MAX_AGE_SECONDS):
    path = cache_path(name)
    if os.path.exists(path):
        try:
            age = time.time() - os.path.getmtime(path)
            if age <= max_age_seconds:
                with open(path, "r") as f:
                    return json.load(f)
        except Exception:
            return None
    return None


def save_cache_json(name: str, data):
    ensure_cache_dir()
    path = cache_path(name)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def fetch_json_with_cache(name: str, url: str, params: dict | None = None, max_age_seconds: int = CACHE_MAX_AGE_SECONDS, local_fallbacks: list[str] | None = None):
    # Return fresh cache if available
    cached = load_cache_if_fresh(name, max_age_seconds)
    if cached is not None:
        return cached
    # Try remote
    try:
        data = http_get_json(url, params)
        save_cache_json(name, data)
        return data
    except Exception:
        # On failure, try stale cache
        stale_path = cache_path(name)
        if os.path.exists(stale_path):
            with open(stale_path, "r") as f:
                return json.load(f)
        # Then try optional local fallbacks
        if local_fallbacks:
            for p in local_fallbacks:
                if os.path.exists(p):
                    with open(p, "r") as f:
                        data = json.load(f)
                        # Save to cache for next time
                        try:
                            save_cache_json(name, data)
                        except Exception:
                            pass
                        return data
        raise


def load_local_json(path: str):
    with open(path, "r") as f:
        return json.load(f)


def fetch_specialities():
    data = fetch_json_with_cache(
        name="specialities.json",
        url=URL_SPECIALITIES,
        params=None,
        local_fallbacks=["specialities.json"],
    )
    items = data.get("specialities") or data.get("items") or data
    result = []
    if isinstance(items, list):
        for it in items:
            code = it.get("id") or it.get("code") or it.get("value") or it.get("key")
            name = it.get("name") or it.get("description") or it.get("label") or code
            if code and name:
                result.append({"code": str(code).strip(), "name": str(name).strip()})
    return sorted(result, key=lambda x: x["name"].lower())


def fetch_plans(cover_start: str):
    data = fetch_json_with_cache(
        name=f"plansummary_{cover_start}.json",
        url=URL_PLANSUMMARY,
        params={"coverStart": cover_start},
        local_fallbacks=["plansummary.json"],
    )
    # Try common shapes
    candidates = []
    containers = []
    for key in ("plans", "planSummaries", "items", "data"):
        if isinstance(data, dict) and key in data and isinstance(data[key], list):
            containers.append(data[key])
    if not containers and isinstance(data, list):
        containers.append(data)
    for arr in containers:
        for it in arr:
            name = (
                it.get("name")
                or it.get("planName")
                or it.get("productName")
                or it.get("displayName")
            )
            if name:
                candidates.append(str(name).strip())
    # De-duplicate while preserving order
    seen = set()
    out = []
    for n in candidates:
        ln = n.lower()
        if ln not in seen:
            out.append(n)
            seen.add(ln)
    return out


def fetch_hospitals():
    data = fetch_json_with_cache(
        name="approved-hospitals.json",
        url=URL_HOSPITALS,
        params=None,
        local_fallbacks=["approved-hospitals.json"],
    )
    hospitals = data.get("hospitals") or data
    return hospitals


def fetch_consultants_by_speciality(speciality_code: str):
    params = {"countyId": "", "hospitalId": "", "specialityId": speciality_code}
    data = fetch_json_with_cache(
        name=f"consultants_{speciality_code.upper()}.json",
        url=URL_CONSULTANTS,
        params=params,
        local_fallbacks=[
            f"consultants_{speciality_code.lower()}.json",
            f"consultants_{speciality_code.upper()}.json",
            "dermatologists.json" if speciality_code.upper() == "DERM" else "",
        ],
    )
    return data.get("consultants") or data


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "report"


def print_available_specialities(specialities: list[dict]):
    print("Available specialities:")
    for it in specialities:
        print(f"- {it['code']}: {it['name']}")


def print_available_plans(plans: list[str]):
    print("Available plans:")
    for name in plans:
        print(f"- {name}")


def build_pdf(consultants: list, hospitals: list, speciality_name: str, plan_name: str, out_path: str):
    hospitals_dict = {h.get("id"): h for h in hospitals}

    doc = SimpleDocTemplate(out_path, pagesize=landscape(letter))
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    subtitle_style = styles["BodyText"]
    cell_style = ParagraphStyle(
        name="Cell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
    )

    title = Paragraph(f"List of {speciality_name} Consultants", title_style)
    sub = Paragraph(f"Plan: {plan_name}", subtitle_style)
    elements.append(title)
    elements.append(sub)
    elements.append(Spacer(1, 0.2 * inch))

    headers = [
        "ID",
        "Name",
        "Participating",
        "Speciality Descriptions",
        "Associated Hospitals",
    ]
    table_data = [headers]

    for c in consultants:
        assoc_lines = []
        for hid in c.get("hospitals", []) or []:
            h = hospitals_dict.get(hid)
            if h:
                name = h.get("name", "Unknown")
                county = h.get("county", "Unknown")
                phone_raw = h.get("phone") or h.get("phoneNo")
                if phone_raw and str(phone_raw).strip():
                    phone_markup = f"<b>{xml_escape(str(phone_raw))}</b>"
                else:
                    phone_markup = "N/A"
                assoc_lines.append(
                    f"{xml_escape(str(name))} ({xml_escape(str(county))}): {phone_markup}"
                )
        assoc_html = "<br/>".join(assoc_lines) if assoc_lines else "N/A"
        assoc_para = Paragraph(assoc_html, cell_style)

        name_text = xml_escape(c.get("name", ""))
        name_para = Paragraph(name_text, cell_style)
        row = [
            str(c.get("id", "")),
            name_para,
            c.get("participating", ""),
            c.get("speciality_descriptions", ""),
            assoc_para,
        ]
        table_data.append(row)

    col_widths = [0.7 * inch, 2.2 * inch, 0.8 * inch, 1.8 * inch, 4.5 * inch]
    table = Table(table_data, colWidths=col_widths)
    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
            ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
        ]
    )
    table.setStyle(table_style)
    elements.append(table)

    doc.build(elements)


def main():
    parser = argparse.ArgumentParser(description="Generate Laya consultants PDF")
    parser.add_argument(
        "--plan",
        "-p",
        default="360 care select",
        help="Plan name (default: 360 care select)",
    )
    parser.add_argument(
        "--speciality",
        "-s",
        help="Speciality code or name (e.g. DERM or Dermatology)",
    )
    parser.add_argument(
        "--cover-start",
        default=str(date.today()),
        help="Cover start date YYYY-MM-DD for plan listing",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output PDF path (default auto from speciality and plan)",
    )

    args = parser.parse_args()

    no_args = len(sys.argv) == 1
    plan_arg_provided = any(a in sys.argv for a in ("--plan", "-p"))
    spec_arg_provided = any(a in sys.argv for a in ("--speciality", "-s"))

    specialities = fetch_specialities()

    if no_args:
        parser.print_help()
        print("")
        plans = fetch_plans(args.cover_start)
        print_available_plans(plans)
        print("")
        print_available_specialities(specialities)
        return

    # If speciality missing, list available specialities and exit
    if not args.speciality:
        print_available_specialities(specialities)
        return

    code_by_name = {it["name"].lower(): it["code"] for it in specialities}
    name_by_code = {it["code"].upper(): it["name"] for it in specialities}

    user_spec = args.speciality.strip()
    if user_spec.upper() in name_by_code:
        spec_code = user_spec.upper()
        spec_name = name_by_code[spec_code]
    else:
        spec_code = code_by_name.get(user_spec.lower())
        spec_name = user_spec
    if not spec_code:
        print("Unknown speciality. Choose one of:")
        print_available_specialities(specialities)
        sys.exit(1)

    plans = fetch_plans(args.cover_start)
    plan_name = args.plan.strip()
    plan_lc = plan_name.lower()
    matched_plan = None
    for p in plans:
        if p.lower() == plan_lc:
            matched_plan = p
            break
    if matched_plan is None:
        print("Unknown plan. Choose one of:")
        print_available_plans(plans)
        sys.exit(1)

    hospitals = fetch_hospitals()
    consultants = fetch_consultants_by_speciality(spec_code)

    out_path = args.output
    if not out_path:
        out_path = f"consultants_{slugify(spec_code)}_{slugify(matched_plan)}.pdf"

    build_pdf(consultants, hospitals, spec_name, matched_plan, out_path)
    print(f"PDF generated successfully: {out_path}")


if __name__ == "__main__":
    main()
