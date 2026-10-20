"""Built-in procedure templates seeded into a new database.

Extracted verbatim from ``DatabaseManager._get_default_templates`` (M43 database.py
split); the method remains and delegates here. Pure data: no ORM or session use.
"""


def default_procedure_templates() -> list:
    """Return a fresh list of the built-in procedure templates (callers may mutate it)."""
    return [
        {
            "name": "7\" Liner Running & Installation",
            "procedure_type": "liner_running",
            "description": "Complete procedure for 7-inch liner running and installation",
            "is_default": True,
            "template_hse_json": [
                "There is always time to rig up and operate safely: Take 'time-out', if necessary.",
                "Pre-plan the job ahead, don't run afterwards.",
                "Focus on falling objects - Avoid loose items on rig-floor and all decks below.",
                "All equipment used above 2m has to be secured with wire.",
                "No work at two levels without a barrier in between.",
                "Hold PJSM and make sure all personnel involved are aware of safety issues.",
            ],
            "template_checklist_json": [
                {"category": "Safety", "item": "Ensure all personnel involved in the job have proper PPE.", "responsible": "WSS"},
                {"category": "Safety", "item": "Justify everyone that HSE issues are superior to any other issues and hold PJSM before each job.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Ensure wear bushing is out.", "responsible": "Driller"},
                {"category": "Equipment", "item": "Check all equipment is on-site and in good condition.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Gauge the OD of the liner drift. Refer to API Spec 5CT.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Rabbit/drift all liner and strap.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Check all liner threads.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Ensure no debris is inside liner joints.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Check liner hanger assembly and accessories.", "responsible": "Baker/Weatherford"},
                {"category": "Equipment", "item": "Ensure the LDC, collar & shoe are PDC drillable.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Make sure power tong jaws are suitable for 7\" liner.", "responsible": "Driller"},
                {"category": "Materials", "item": "Ensure enough number of stop collars are available.", "responsible": "WSS"},
                {"category": "Materials", "item": "Centralizer types & program available & checked.", "responsible": "WSS"},
                {"category": "Materials", "item": "Prepare, clean, drift and dope all the joints on pipe rack.", "responsible": "WSS"},
                {"category": "Safety", "item": "Make sure the snub line is the correct size and length and certified.", "responsible": "Driller"},
                {"category": "Safety", "item": "Make sure annular preventer functioning.", "responsible": "Driller"},
            ],
            "template_steps_json": [
                {
                    "step_number": 1,
                    "activity": "Hold pre-job safety meeting for liner installation operations on rig floor.",
                    "parallel": "Focus on: Falling object & heavy equipment.",
                    "caution": ""
                },
                {
                    "step_number": 2,
                    "activity": "R/U liner running equipment. Use torque/turn monitoring system.",
                    "parallel": "Ensure wear bushing is out.\nCheck elevator and lock pins.\nCheck stabbing board.",
                    "caution": ""
                },
                {
                    "step_number": 3,
                    "activity": "M/U shoe & first joint. Use bakerlok for pin of 1st Joint on shoe. Run & check float with torchlight.",
                    "parallel": "Shoe & collar float valves should be inspected and checked before making up.\nVisually inspect shoe joint for debris.",
                    "caution": "Apply Bakerlok on pin of 1st Joint on shoe, pin of collar, pin of LDC."
                },
                {
                    "step_number": 4,
                    "activity": "M/U float collar. Use bakerlok for pin of float collar. Run & check float.",
                    "parallel": "While picking up, one signal man to guide crane operator to prevent breaking the shoe.",
                    "caution": "Clean thread of shoe and collar completely."
                },
                {
                    "step_number": 5,
                    "activity": "M/U LDC. Use bakerlok for pin of LDC. Break circulation and check float valve.",
                    "parallel": "",
                    "caution": "Liner Tally must be followed. Any changes to be noted and WSS informed immediately."
                },
                {
                    "step_number": 6,
                    "activity": "Run liner as per Tally. F/U all first 5 joints, then F/U every 7 joints. Install centralizers per program.",
                    "parallel": "Mud loggers to prepare swab/surge calculations.\nRunning speed: max 8 stands/hr.",
                    "caution": "Do not exceed 300-500 psi during circulation."
                },
                {
                    "step_number": 7,
                    "activity": "M/U liner hanger assembly as per job specialist instruction.",
                    "parallel": "Ensure the tally is followed.",
                    "caution": "Make sure of proper connection between hanger and setting tool before removing the slips."
                },
                {
                    "step_number": 8,
                    "activity": "Continue RIH on 5\" DPs. F/U each 10 stands. Break circulation and check free circulation.",
                    "parallel": "Running speed: max 10 stands/hr excluding F/U time.",
                    "caution": "Rotary table should be locked during liner job. Avoid any Left Hand Rotation."
                },
                {
                    "step_number": 9,
                    "activity": "Continue RIH to liner setting depth. Wash down last stand to bottom. Tag bottom (max 10klb).",
                    "parallel": "Confirm hole bottom by tagging.\nMinimize stopping time in open hole.",
                    "caution": "Do not jerk the string at any time."
                },
                {
                    "step_number": 10,
                    "activity": "Drop ball and continue circulation to land the ball on LDC ball catcher. Set liner hanger.",
                    "parallel": "In case of failure in setting the hanger, contact office for contingency plan.",
                    "caution": "Increase pressure to 1500 psi to set liner hanger. Then increase to 3000 psi to shear ball catcher."
                },
                {
                    "step_number": 11,
                    "activity": "Release setting tool by rotating string 20 turns forwards. Make sure it is free.",
                    "parallel": "Mark DP at surface - be cautious not to pull setting tool out of POB.",
                    "caution": "Prepare cement slurry so cementing can start ASAP after liner setting."
                },
                {
                    "step_number": 12,
                    "activity": "Make up cement head and prepare for cement job. Hold pre-cement safety meeting.",
                    "parallel": "Connect cementing lines to cement manifold.",
                    "caution": "Check number of liner joints left on racks with pipe tally."
                },
            ]
        },
        {
            "name": "Surface Casing Running",
            "procedure_type": "casing_running",
            "description": "Procedure for running and cementing surface casing",
            "is_default": True,
            "template_hse_json": [
                "Ensure all personnel have valid certifications.",
                "Hold PJSM before operation.",
                "Monitor casing weights during running.",
            ],
            "template_checklist_json": [
                {"category": "Safety", "item": "Hold PJSM for casing running operations.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Drift and strap all casing joints.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Check float equipment (shoe, collar).", "responsible": "WSS"},
                {"category": "Equipment", "item": "Prepare centralizer program.", "responsible": "Engineer"},
                {"category": "Equipment", "item": "Check power tong for correct dies.", "responsible": "Driller"},
            ],
            "template_steps_json": [
                {"step_number": 1, "activity": "Hold pre-job safety meeting.", "parallel": "Review hazards.", "caution": ""},
                {"step_number": 2, "activity": "R/U casing running equipment.", "parallel": "Check elevator.", "caution": ""},
                {"step_number": 3, "activity": "M/U shoe joint and float collar.", "parallel": "Test floats.", "caution": ""},
                {"step_number": 4, "activity": "Run casing as per tally.", "parallel": "Fill up every 5 joints.", "caution": "Monitor surge pressures."},
            ]
        },
        {
            "name": "Primary Cementing",
            "procedure_type": "cementing",
            "description": "Primary cementing procedure for casing strings",
            "is_default": True,
            "template_hse_json": [
                "Hold PJSM with all cementing crew.",
                "Ensure all pressure equipment is tested.",
                "Have kill line available.",
            ],
            "template_checklist_json": [
                {"category": "Safety", "item": "Hold PJSM for cementing operations.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Test cement head and all connections.", "responsible": "Cementer"},
                {"category": "Materials", "item": "Confirm cement design and additives on location.", "responsible": "Cementer"},
                {"category": "Equipment", "item": "Check displacement calculations.", "responsible": "Cementer"},
            ],
            "template_steps_json": [
                {"step_number": 1, "activity": "Hold pre-job safety meeting.", "parallel": "", "caution": ""},
                {"step_number": 2, "activity": "Mix and pump spacer.", "parallel": "Monitor returns.", "caution": ""},
                {"step_number": 3, "activity": "Release top plug.", "parallel": "", "caution": ""},
                {"step_number": 4, "activity": "Displace cement.", "parallel": "Monitor ECD.", "caution": "Do not exceed max ECD."},
                {"step_number": 5, "activity": "Bump top plug. Record final pressure.", "parallel": "", "caution": ""},
                {"step_number": 6, "activity": "WOC (Wait on Cement).", "parallel": "", "caution": ""},
            ]
        },
        {
            "name": "BOP Test Procedure",
            "procedure_type": "bop_test",
            "description": "Routine BOP pressure testing procedure",
            "is_default": True,
            "template_hse_json": [
                "Ensure all personnel are clear of BOP area during testing.",
                "Have kill line and choke manifold ready.",
                "Verify all gauges are calibrated.",
            ],
            "template_checklist_json": [
                {"category": "Safety", "item": "Hold PJSM for BOP test.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Verify all BOP components are properly installed.", "responsible": "Company Man"},
                {"category": "Equipment", "item": "Check accumulator pressure (min 200 psi above WHP).", "responsible": "Driller"},
                {"category": "Equipment", "item": "Test all pressure gauges.", "responsible": "Driller"},
            ],
            "template_steps_json": [
                {"step_number": 1, "activity": "Hold PJSM.", "parallel": "", "caution": ""},
                {"step_number": 2, "activity": "Function test annular preventer - open and close.", "parallel": "", "caution": ""},
                {"step_number": 3, "activity": "Function test pipe rams.", "parallel": "", "caution": ""},
                {"step_number": 4, "activity": "Pressure test annular to low test pressure (200-300 psi) for 5 min.", "parallel": "", "caution": ""},
                {"step_number": 5, "activity": "Pressure test pipe rams to rated WP.", "parallel": "", "caution": "Hold for 10 minutes."},
                {"step_number": 6, "activity": "Test choke and kill lines.", "parallel": "", "caution": ""},
                {"step_number": 7, "activity": "Function test shear rams.", "parallel": "", "caution": "Do NOT pressure test shear rams."},
                {"step_number": 8, "activity": "Record all test results and report to Company Man.", "parallel": "", "caution": ""},
            ]
        },
        {
            "name": "Well Kill - Driller's Method",
            "procedure_type": "well_kill",
            "description": "Well kill using Driller's Method (two circulation method)",
            "is_default": True,
            "template_hse_json": [
                "Immediately alert all personnel on rig floor.",
                "Close BOP - do not stop pumps abruptly.",
                "Record SIDPP and SICP.",
                "Calculate kill mud weight.",
                "No smoking near degasser.",
            ],
            "template_checklist_json": [
                {"category": "Safety", "item": "All personnel at stations.", "responsible": "Company Man"},
                {"category": "Equipment", "item": "BOP closed and confirmed.", "responsible": "Driller"},
                {"category": "Equipment", "item": "Kill sheet completed.", "responsible": "WSS"},
                {"category": "Equipment", "item": "SCR test recent and valid.", "responsible": "Driller"},
            ],
            "template_steps_json": [
                {"step_number": 1, "activity": "Detect kick. Stop rotation. Pick up off bottom.", "parallel": "Alert Company Man immediately.", "caution": ""},
                {"step_number": 2, "activity": "Flow check. If flowing, shut in well.", "parallel": "Do not shut in with string in OH if possible.", "caution": ""},
                {"step_number": 3, "activity": "Close pipe rams (or annular). Record SIDPP and SICP.", "parallel": "Record after pressures stabilize.", "caution": ""},
                {"step_number": 4, "activity": "Calculate: Kill MW = Original MW + SIDPP/(0.052×TVD)", "parallel": "Complete kill sheet.", "caution": ""},
                {"step_number": 5, "activity": "FIRST CIRCULATION: Circulate kick out with original mud weight.", "parallel": "Maintain constant BHP by holding SIDPP constant.", "caution": "Monitor choke pressure continuously."},
                {"step_number": 6, "activity": "Weight up mud to kill weight.", "parallel": "Continue circulating if needed.", "caution": ""},
                {"step_number": 7, "activity": "SECOND CIRCULATION: Circulate kill weight mud around.", "parallel": "Keep BHP constant.", "caution": "Reduce choke gradually as kill mud reaches bit."},
                {"step_number": 8, "activity": "Verify well is dead. Bleed off pressure slowly.", "parallel": "", "caution": ""},
                {"step_number": 9, "activity": "Open BOP. Resume normal operations.", "parallel": "Document all events.", "caution": ""},
            ]
        },
        {
            "name": "Tripping Out of Hole",
            "procedure_type": "tripping",
            "description": "Standard POOH procedure",
            "is_default": True,
            "template_hse_json": [
                "Flow check before and during tripping.",
                "Monitor pit levels continuously.",
                "Fill hole every 5 stands.",
            ],
            "template_checklist_json": [
                {"category": "Safety", "item": "Short trip completed and results satisfactory.", "responsible": "WSS"},
                {"category": "Equipment", "item": "Fill-up pump ready.", "responsible": "Driller"},
                {"category": "Equipment", "item": "Trip tank calibrated.", "responsible": "Mud Logger"},
            ],
            "template_steps_json": [
                {"step_number": 1, "activity": "Condition mud. Perform flow check.", "parallel": "Verify mud weight.", "caution": ""},
                {"step_number": 2, "activity": "Pull out slowly. Observe for swab.", "parallel": "Monitor trip tank.", "caution": ""},
                {"step_number": 3, "activity": "Fill hole every 5 stands. Record volumes.", "parallel": "Compare fill volume with theoretical.", "caution": "Any discrepancy: stop and investigate."},
                {"step_number": 4, "activity": "Pull past casing shoe. Record P/U weight.", "parallel": "", "caution": ""},
                {"step_number": 5, "activity": "Continue POOH to surface.", "parallel": "", "caution": ""},
                {"step_number": 6, "activity": "L/D BHA. Inspect bit.", "parallel": "Record bit dull grade.", "caution": ""},
            ]
        },
    ]
