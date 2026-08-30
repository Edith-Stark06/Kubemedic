"""Dashboard verification script — Step 5.
Run: python dashboard/tests/verify_dashboard.py
"""
import asyncio
import copy
import sys

sys.path.insert(0, ".")

from httpx import AsyncClient, ASGITransport
from dashboard.app import app
from dashboard.api_adapter import _MOCK_INCIDENTS

_ORIG = copy.deepcopy(_MOCK_INCIDENTS)


async def check():
    # Reset mock to PENDING_APPROVAL state
    _MOCK_INCIDENTS.clear()
    _MOCK_INCIDENTS.update(copy.deepcopy(_ORIG))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        checks = []

        r = await c.get("/")
        checks.append(("1.  App starts (GET /)",                   r.status_code == 200,       r.status_code))
        checks.append(("2.  Index renders KubeMedic brand",         "KubeMedic" in r.text,      "ok" if "KubeMedic" in r.text else "MISSING"))

        r_css = await c.get("/static/style.css")
        checks.append(("3.  CSS loads",                             r_css.status_code == 200,   r_css.status_code))

        r_js = await c.get("/static/app.js")
        checks.append(("4.  JS loads",                              r_js.status_code == 200,    r_js.status_code))

        r_inc = await c.get("/incident/INC-501")
        checks.append(("5.  Incident page loads",                   r_inc.status_code == 200,   r_inc.status_code))
        checks.append(("6.  IBM Bob Analysis panel present",        "IBM Bob Analysis" in r_inc.text,     "ok" if "IBM Bob Analysis" in r_inc.text else "MISSING"))
        checks.append(("7.  Human Final Review section present",    "Human Final Review" in r_inc.text,   "ok" if "Human Final Review" in r_inc.text else "MISSING"))
        checks.append(("8.  Approve button present",                "btn-approve" in r_inc.text,           "ok" if "btn-approve" in r_inc.text else "MISSING"))
        checks.append(("9.  Reject button present",                 "btn-reject" in r_inc.text,            "ok" if "btn-reject" in r_inc.text else "MISSING"))
        checks.append(("10. Rejection dialog in DOM (hidden)",      "dialog-overlay" in r_inc.text,        "ok" if "dialog-overlay" in r_inc.text else "MISSING"))
        checks.append(("11. Feedback textarea in DOM",              "rejection-feedback-input" in r_inc.text, "ok" if "rejection-feedback-input" in r_inc.text else "MISSING"))

        # 12+13. JS field name contract — strip comment lines before checking
        js = r_js.text
        js_code = "\n".join(
            line for line in js.splitlines()
            if not line.strip().startswith("//") and not line.strip().startswith("*")
        )
        uses_feedback_field = "feedback: feedback" in js_code
        uses_wrong_name     = "rejection_feedback" in js_code
        checks.append(("12. JS sends field named 'feedback' (correct)",         uses_feedback_field, "ok" if uses_feedback_field else "NOT FOUND IN CODE"))
        checks.append(("13. JS does NOT use 'rejection_feedback' in code",      not uses_wrong_name, "ok" if not uses_wrong_name else "WRONG NAME IN CODE"))

        # 14. Empty feedback blocked
        r_empty = await c.post("/api/reject", json={"incident_id": "INC-501", "feedback": ""})
        checks.append(("14. Empty feedback -> 422",                  r_empty.status_code == 422, r_empty.status_code))

        # 15. Whitespace blocked
        r_ws = await c.post("/api/reject", json={"incident_id": "INC-501", "feedback": "   "})
        checks.append(("15. Whitespace-only feedback -> 422",        r_ws.status_code == 422,    r_ws.status_code))

        # 16-19. Valid rejection
        feedback_text = "This deployment is an approved maintenance activity, do not roll back."
        r_rej = await c.post("/api/reject", json={
            "incident_id": "INC-501",
            "approver": "verona",
            "feedback": feedback_text,
        })
        checks.append(("16. Valid rejection -> 200",                 r_rej.status_code == 200,   r_rej.status_code))
        if r_rej.status_code == 200:
            data = r_rej.json()
            checks.append(("17. State = FEEDBACK_RECORDED after reject", data["state"] == "FEEDBACK_RECORDED", data.get("state")))
            checks.append(("18. decision.feedback stored verbatim",  data["human_decision"]["feedback"] == feedback_text, "ok" if data["human_decision"]["feedback"] == feedback_text else "MISMATCH"))
            checks.append(("19. execution is None after rejection",   data["execution"] is None,  "ok" if data["execution"] is None else "NON-NULL"))

        # 20-24. Rejection renders correctly in page
        r_page = await c.get("/incident/INC-501")
        checks.append(("20. REJECTED shown in post-rejection page",  "REJECTED" in r_page.text,     "ok" if "REJECTED" in r_page.text else "MISSING"))
        checks.append(("21. Feedback text verbatim in page",         feedback_text in r_page.text,   "ok" if feedback_text in r_page.text else "MISSING"))
        not_executed = "NOT executed" in r_page.text or "was NOT executed" in r_page.text
        checks.append(("22. 'NOT executed' shown in page",           not_executed,                   "ok" if not_executed else "MISSING"))
        checks.append(("23. Timeline panel present",                 "panel-timeline" in r_page.text, "ok" if "panel-timeline" in r_page.text else "MISSING"))
        # Approve/Reject controls must be gone after decision
        checks.append(("24. Controls gone after rejection",          "btn-approve" not in r_page.text, "ok" if "btn-approve" not in r_page.text else "CONTROLS STILL PRESENT"))

        # 25-27. Approval path (reset first)
        _MOCK_INCIDENTS.clear()
        _MOCK_INCIDENTS.update(copy.deepcopy(_ORIG))
        r_app = await c.post("/api/approve", json={"incident_id": "INC-501", "approver": "alice"})
        checks.append(("25. Approval -> 200",                        r_app.status_code == 200,   r_app.status_code))
        if r_app.status_code == 200:
            d = r_app.json()
            checks.append(("26. Approval state = APPROVED",          d["state"] == "APPROVED",   d.get("state")))
            checks.append(("27. Approval feedback = None",           d["human_decision"]["feedback"] is None, "ok" if d["human_decision"]["feedback"] is None else "NON-NULL"))

        # 28-29. Edge cases
        r404 = await c.get("/incident/DOES-NOT-EXIST")
        checks.append(("28. Unknown incident -> not 500",            r404.status_code != 500,    r404.status_code))

        rh = await c.get("/healthz")
        checks.append(("29. /healthz -> 200",                        rh.status_code == 200,      rh.status_code))

        # Print results (ASCII-safe labels only)
        passed = sum(1 for _, p, _ in checks if p)
        total  = len(checks)
        for label, ok, detail in checks:
            print("  {}  {}  [{}]".format("PASS" if ok else "FAIL", label, detail))
        print()
        print("Result: {}/{} checks passed".format(passed, total))
        failed = [label for label, p, _ in checks if not p]
        if failed:
            print("FAILURES:")
            for f in failed:
                print("  -", f)
            sys.exit(1)
        else:
            print("All checks passed.")


asyncio.run(check())
