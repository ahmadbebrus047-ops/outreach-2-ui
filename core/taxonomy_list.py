"""
Comprehensive list of NUCC taxonomy *descriptions* (classification level),
exactly as NPPES matches them via the `taxonomy_description` query param.

IMPORTANT: NPPES matches these strings exactly (case- and spelling-sensitive).
That is why the UI offers them as a picklist rather than free text -- typing
"family medicine" instead of "Family Medicine" returns zero results.

This is the classification-level set most useful for medical-billing outreach.
It is not the entire 850+ code set (many are sub-specializations that share a
classification description); it covers the practical specialties you'd target.
Blank ("") means "no filter -- all providers".
"""
from __future__ import annotations

TAXONOMY_DESCRIPTIONS: list[str] = [
    "",  # blank = all providers (no taxonomy filter)

    # --- Primary care / general ---
    "Family Medicine",
    "Internal Medicine",
    "General Practice",
    "Pediatrics",
    "Adolescent Medicine",
    "Geriatric Medicine",
    "Preventive Medicine",

    # --- OB/GYN & women's health ---
    "Obstetrics & Gynecology",
    "Gynecology",
    "Obstetrics",
    "Maternal & Fetal Medicine",
    "Midwife",
    "Certified Nurse Midwife",

    # --- Medical specialties ---
    "Allergy & Immunology",
    "Anesthesiology",
    "Cardiovascular Disease",
    "Cardiology",
    "Clinical Cardiac Electrophysiology",
    "Critical Care Medicine",
    "Dermatology",
    "Emergency Medicine",
    "Endocrinology, Diabetes & Metabolism",
    "Gastroenterology",
    "Hematology & Oncology",
    "Hematology",
    "Hospitalist",
    "Infectious Disease",
    "Nephrology",
    "Neurology",
    "Nuclear Medicine",
    "Oncology",
    "Ophthalmology",
    "Pain Medicine",
    "Palliative Care",
    "Pathology",
    "Physical Medicine & Rehabilitation",
    "Psychiatry",
    "Psychiatry & Neurology",
    "Pulmonary Disease",
    "Radiology",
    "Diagnostic Radiology",
    "Interventional Radiology",
    "Rheumatology",
    "Sleep Medicine",
    "Sports Medicine",
    "Urology",

    # --- Surgery ---
    "Surgery",
    "General Surgery",
    "Colon & Rectal Surgery",
    "Neurological Surgery",
    "Orthopaedic Surgery",
    "Otolaryngology",
    "Plastic Surgery",
    "Thoracic Surgery (Cardiothoracic Vascular Surgery)",
    "Vascular Surgery",
    "Hand Surgery",

    # --- Dental ---
    "Dentist",
    "General Practice Dentistry",
    "Orthodontics and Dentofacial Orthopedics",
    "Oral & Maxillofacial Surgery",
    "Endodontics",
    "Periodontics",
    "Pedodontics",
    "Prosthodontics",
    "Dental Hygienist",

    # --- Eye / vision ---
    "Optometrist",
    "Optician",

    # --- Foot ---
    "Podiatrist",

    # --- Chiropractic ---
    "Chiropractor",

    # --- Behavioral / mental health ---
    "Psychologist",
    "Clinical Psychologist",
    "Counselor",
    "Professional Counselor",
    "Clinical Social Worker",
    "Social Worker",
    "Marriage & Family Therapist",
    "Behavior Analyst",
    "Behavioral Health & Social Service Providers",

    # --- Nursing / advanced practice ---
    "Nurse Practitioner",
    "Physician Assistant",
    "Registered Nurse",
    "Licensed Practical Nurse",
    "Clinical Nurse Specialist",
    "Nurse Anesthetist, Certified Registered",

    # --- Therapy / rehab ---
    "Physical Therapist",
    "Occupational Therapist",
    "Speech-Language Pathologist",
    "Audiologist",
    "Respiratory Therapist, Certified",
    "Massage Therapist",
    "Athletic Trainer",

    # --- Pharmacy / dietary ---
    "Pharmacist",
    "Pharmacy",
    "Dietitian, Registered",
    "Nutritionist",

    # --- Diagnostics / other individual ---
    "Specialist",
    "Technician",
    "Acupuncturist",
    "Naturopath",
    "Midwife, Lay",

    # --- Organizations / facilities (entity type 2) ---
    "Clinic/Center",
    "General Acute Care Hospital",
    "Hospital",
    "Skilled Nursing Facility",
    "Nursing Facility/Intermediate Care Facility",
    "Home Health",
    "Hospice Care, Community Based",
    "Pharmacy",
    "Laboratory",
    "Clinical Medical Laboratory",
    "Durable Medical Equipment & Medical Supplies",
    "Ambulance",
    "Urgent Care",
    "Rehabilitation Hospital",
    "Psychiatric Hospital",
    "Ambulatory Surgical",
    "Radiology, Mobile",
    "Physical Therapy",
    "Group",
    "Single Specialty Group",
    "Multi-Specialty Group",
]
