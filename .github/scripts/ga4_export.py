"""Free daily Google Analytics 4 export (no paid connector needed).

Runs in GitHub Actions after the Search Console export (.github/workflows/gsc-daily.yml)
and uses the same service account (secret GSC_SA_JSON). The service account email must be
added in GA4: Admin > Property access management > Add users > Viewer.
The "Google Analytics Data API" must be enabled in the same Google Cloud project.

Writes to <out>/latest/:
  ga4_events_7d.csv          event, count this week, count last week
  ga4_leads_by_page_28d.csv  page, lead event, count (last 28 days)
  ga4_landing_7d.csv         landing page, channel, sessions, engaged sessions (last 7 days)
and appends a "Website enquiries" section to summary.md.

Lead events are the site's twaTrack events (whatsapp_click, call clicks, forms).
Optional variable GA4_PROPERTY (numeric property ID); default below.
"""
import csv, json, os, re, sys

DEFAULT_PROPERTY = "555751922"  # Cowboy Dorms GA4 property (repo variable GA4_PROPERTY overrides)
LEAD_RE = re.compile(r"whatsapp|call|phone|tel|lead|form|enquir|generate_lead|book", re.I)


def main(out_dir):
    raw = os.environ.get("GSC_SA_JSON", "").strip()
    if not raw:
        print("::notice::GSC_SA_JSON secret is not set; skipping the GA4 export.")
        return 0
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    svc = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)
    pid = os.environ.get("GA4_PROPERTY", "").strip() or DEFAULT_PROPERTY
    if not pid:
        print("::notice::GA4_PROPERTY variable is not set; skipping the GA4 export.")
        return 0
    prop = "properties/" + pid

    def run(dims, mets, ranges, limit=10000):
        body = {"dateRanges": ranges, "dimensions": [{"name": d} for d in dims],
                "metrics": [{"name": m} for m in mets], "limit": limit}
        res = svc.properties().runReport(property=prop, body=body).execute()
        out = []
        for r in res.get("rows", []):
            out.append([d["value"] for d in r["dimensionValues"]] +
                       [m["value"] for m in r["metricValues"]])
        return out

    try:
        ev = [r[:1] + ["this"] + r[1:] for r in
              run(["eventName"], ["eventCount"], [{"startDate": "9daysAgo", "endDate": "3daysAgo"}])]
        ev += [r[:1] + ["last"] + r[1:] for r in
               run(["eventName"], ["eventCount"], [{"startDate": "16daysAgo", "endDate": "10daysAgo"}])]
    except Exception as e:  # most likely: API not enabled or no access
        print(f"::warning::GA4 export failed for {prop}: {e}. Check that the Google Analytics "
              "Data API is enabled and the service account has Viewer access in GA4.")
        return 0

    latest = os.path.join(out_dir, "latest")
    os.makedirs(latest, exist_ok=True)
    counts = {}
    for name, rng, n in ev:
        counts.setdefault(name, {"this": 0, "last": 0})[rng] = int(n)
    with open(os.path.join(latest, "ga4_events_7d.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event", "this_week", "last_week"])
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]["this"]):
            w.writerow([k, v["this"], v["last"]])

    month = [{"startDate": "30daysAgo", "endDate": "3daysAgo"}]
    leads = [r for r in run(["pagePath", "eventName"], ["eventCount"], month) if LEAD_RE.search(r[1])]
    leads.sort(key=lambda r: -int(r[2]))
    with open(os.path.join(latest, "ga4_leads_by_page_28d.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "event", "count"])
        w.writerows(leads)

    landing = run(["landingPage", "sessionDefaultChannelGroup"], ["sessions", "engagedSessions"],
                  [{"startDate": "9daysAgo", "endDate": "3daysAgo"}])
    landing.sort(key=lambda r: -int(r[2]))
    with open(os.path.join(latest, "ga4_landing_7d.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["landing_page", "channel", "sessions", "engaged_sessions"])
        w.writerows(landing)

    lead_ev = {k: v for k, v in counts.items() if LEAD_RE.search(k)}
    organic = sum(int(r[2]) for r in landing if r[1] == "Organic Search")
    lines = ["", "## Website enquiries (Google Analytics, same weeks)", ""]
    lines += [f"- {k}: {v['this']} this week / {v['last']} last week"
              for k, v in sorted(lead_ev.items(), key=lambda kv: -kv[1]["this"])] or ["- no lead events found"]
    lines += [f"- Organic Search sessions this week: {organic}", "",
              "Top pages by enquiries (28 days):", ""]
    lines += [f"- {r[0]} – {r[1]}: {r[2]}" for r in leads[:10]] or ["- none yet"]
    with open(os.path.join(latest, "summary.md"), "a") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out"))
