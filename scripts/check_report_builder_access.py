"""One-off diagnostic: is PriceLabs' Report Builder reachable from a plain
Customer API key, or only through an authenticated session (dashboard/MCP)?

If this succeeds and finds "Master Sheet - TB" (or any template with the
pacing/pickup fields the spec wants), we should almost certainly switch
data_pull.py to just call it directly instead of self-computing pickup via
the local snapshot cache -- it would give correct, complete pickup values
from day one instead of needing 30-60 days of accumulated history.

If it 403s/404s, that confirms the self-computed approach is necessary,
not just a cautious default.

Run from the project root:
    python -m scripts.check_report_builder_access
"""

import sys

from pacing_tracker.api_client import PriceLabsAPIError, PriceLabsClient


def main():
    client = PriceLabsClient()

    print("Step 1: GET report_builder/templates ...")
    try:
        templates_resp = client.get_report_builder_templates()
    except PriceLabsAPIError as exc:
        print(f"  FAILED: {exc}")
        print("\nConclusion: Report Builder is NOT reachable from this API key.")
        print("The self-computed pickup approach in snapshot_cache.py is necessary.")
        sys.exit(1)

    print("  Succeeded. Raw response (first 2000 chars):")
    print(str(templates_resp)[:2000])

    templates = templates_resp.get("data", templates_resp)
    if isinstance(templates, dict):
        templates = templates.get("templates", [])
    if not isinstance(templates, list):
        print("\nUnexpected shape -- couldn't find a template list to search. Stopping here.")
        return

    master_sheet = next((t for t in templates if "Master Sheet" in str(t.get("name", ""))), None)
    if not master_sheet:
        print("\n'Master Sheet - TB' not found in this key's template list.")
        print("(It may be account-specific / owned by a different user.) Stopping here.")
        return

    template_id = master_sheet.get("templateId") or master_sheet.get("id")
    print(f"\nFound template: {master_sheet.get('name')} (id={template_id})")

    print(f"\nStep 2: POST report_builder/data for template_id={template_id} ...")
    try:
        data_resp = client.get_report_builder_data(template_id)
    except PriceLabsAPIError as exc:
        print(f"  FAILED: {exc}")
        print("\nConclusion: templates are listable but data isn't fetchable with this key.")
        sys.exit(1)

    print("  Succeeded. Raw response (first 2000 chars):")
    print(str(data_resp)[:2000])

    payload = data_resp.get("data", data_resp)
    request_id = payload.get("request_id") if isinstance(payload, dict) else None
    if request_id:
        print(f"\nAsync job started (request_id={request_id}). Polling...")
        import time

        for _ in range(20):
            time.sleep(3)
            poll_resp = client.poll_report_builder_data(request_id)
            poll_payload = poll_resp.get("data", poll_resp)
            if isinstance(poll_payload, dict) and poll_payload.get("report_data"):
                print("  Got report_data. First record:")
                print(poll_payload["report_data"][0])
                return
        print("  Gave up after 60 seconds of polling.")
    else:
        report_data = payload.get("report_data") if isinstance(payload, dict) else None
        if report_data:
            print("\nGot report_data immediately. First record:")
            print(report_data[0])


if __name__ == "__main__":
    main()
