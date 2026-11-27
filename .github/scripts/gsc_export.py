"""Free daily Google Search Console export (no paid connector needed).

Runs in GitHub Actions (.github/workflows/gsc-daily.yml). Uses a Google Cloud
service account (free) that has been added as a user on the Search Console
property. Writes CSV files that the daily SEO task reads from the `seo-data`
branch:

  latest/queries_7d.csv        query, clicks, impressions, ctr, position (last 7 days)
  latest/queries_prev7d.csv    same for the 7 days before that
  latest/pages_7d.csv          page, clicks, impressions, ctr, position (last 7 days)
  latest/query_page_28d.csv    query, page, ... (last 28 days)
  latest/query_country_28d.csv query, country, ... (last 28 days)
  latest/summary.md            the target keywords, this week vs last week
  history/YYYY-MM-DD/...       a copy of each day's files

Search Console data lags 2-3 days, so "last 7 days" ends 3 days ago.
Secret GSC_SA_JSON = the service account's JSON key. Optional variable GSC_SITE
(e.g. "sc-domain:cowboydorms.com" or "https://cowboydorms.com/").
"""
import csv, datetime as dt, json, os, sys

# Cowboy Dorms keyword groups
SEGMENTS = {
    "Stay near Cochin airport": [
        "stay near cochin airport", "stay near kochi airport", "hotel near cochin airport",
        "budget stay near cochin airport", "cheap stay near cochin airport", "rooms near cochin airport",
        "accommodation near cochin airport", "lodge near cochin airport",
    ],
    "Hostel / dormitory": [
        "hostel near cochin airport", "hostel near kochi airport", "dormitory near cochin airport",
        "ac dormitory near cochin airport", "dorm near kochi airport", "backpackers hostel kochi",
        "hostel in nedumbassery", "dormitory in kochi",
    ],
    "Short / hourly stay": [
        "hourly stay near cochin airport", "hourly rooms near kochi airport", "transit stay cochin airport",
        "layover stay kochi airport", "short stay near cochin airport", "fresh up near cochin airport",
    ],
    "Nearby places": [
        "stay in nedumbassery", "stay in angamaly", "stay in aluva", "hostel in aluva",
        "stay near tcs ion digital zone aluva", "stay near sabarimala kochi airport",
    ],
}
TARGETS = [k for ks in SEGMENTS.values() for k in ks]
SEGMENT_RULES = {
    "Stay near Cochin airport": lambda q: AIRPORT(q) and not DORM(q) and not SHORT(q),
    "Hostel / dormitory": lambda q: DORM(q),
    "Short / hourly stay": lambda q: SHORT(q) and not DORM(q),
    "Nearby places": lambda q: PLACE(q) and not AIRPORT(q) and not DORM(q),
}
AIRPORT = lambda q: any(w in q for w in ("airport", "cial", "nedumbassery"))
DORM = lambda q: any(w in q for w in ("hostel", "dorm", "backpack", "bunk", "bed"))
SHORT = lambda q: any(w in q for w in ("hour", "transit", "layover", "short stay", "fresh up", "freshup"))
PLACE = lambda q: any(w in q for w in ("aluva", "angamaly", "athani", "kalady", "nedumbassery", "tcs", "kochi", "cochin"))

def main(out_dir):
    raw = os.environ.get("GSC_SA_JSON", "").strip()
    if not raw:
        print("::notice::GSC_SA_JSON secret is not set yet; skipping the export.")
        return 0
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    site = os.environ.get("GSC_SITE", "").strip()
    if not site:
        sites = [s["siteUrl"] for s in svc.sites().list().execute().get("siteEntry", [])
                 if "cowboydorms.com" in s["siteUrl"]]
        if not sites:
            print("::error::The service account cannot see any cowboydorms.com property. "
                  "Add its email as a user in Search Console (Settings > Users and permissions).")
            return 1
        site = sorted(sites, key=lambda s: not s.startswith("sc-domain:"))[0]
    print("Property:", site)

    end = dt.date.today() - dt.timedelta(days=3)
    w1 = (end - dt.timedelta(days=6), end)
    w0 = (w1[0] - dt.timedelta(days=7), w1[0] - dt.timedelta(days=1))
    m = (end - dt.timedelta(days=27), end)

    def q(rng, dims):
        rows, start = [], 0
        while True:
            body = {"startDate": rng[0].isoformat(), "endDate": rng[1].isoformat(),
                    "dimensions": dims, "rowLimit": 25000, "startRow": start, "type": "web"}
            r = svc.searchanalytics().query(siteUrl=site, body=body).execute().get("rows", [])
            rows += r
            if len(r) < 25000:
                return rows
            start += 25000

    def save(name, rows, dims):
        path = os.path.join(out_dir, "latest", name)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(dims + ["clicks", "impressions", "ctr", "position"])
            for r in sorted(rows, key=lambda r: -r["impressions"]):
                w.writerow(r["keys"] + [r["clicks"], r["impressions"], round(r["ctr"], 4), round(r["position"], 1)])
        return rows

    os.makedirs(os.path.join(out_dir, "latest"), exist_ok=True)
    cur = save("queries_7d.csv", q(w1, ["query"]), ["query"])
    prev = save("queries_prev7d.csv", q(w0, ["query"]), ["query"])
    save("pages_7d.csv", q(w1, ["page"]), ["page"])
    save("query_page_28d.csv", q(m, ["query", "page"]), ["query", "page"])
    save("query_country_28d.csv", q(m, ["query", "country"]), ["query", "country"])

    c = {r["keys"][0]: r for r in cur}
    p = {r["keys"][0]: r for r in prev}
    lines = [f"# Search Console summary ({site})", "",
             f"This week: {w1[0]} to {w1[1]} · last week: {w0[0]} to {w0[1]}", "",
             "## Segment totals (all queries, this week / last week)", "",
             "| Segment | Impressions | Clicks |", "|---|---|---|"]
    for name, rule in SEGMENT_RULES.items():
        ci = [r for r in cur if rule(r["keys"][0].lower())]
        pi = [r for r in prev if rule(r["keys"][0].lower())]
        lines.append(f"| {name} | {int(sum(r['impressions'] for r in ci))} / {int(sum(r['impressions'] for r in pi))} "
                     f"| {int(sum(r['clicks'] for r in ci))} / {int(sum(r['clicks'] for r in pi))} |")
    fmt = lambda r, k: ("-" if r is None else (round(r[k], 1) if k == "position" else int(r[k])))
    for name, keys in SEGMENTS.items():
        lines += ["", f"## {name}", "",
                  "| Keyword | Position (this / last) | Impressions (this / last) | Clicks (this / last) |",
                  "|---|---|---|---|"]
        for k in keys:
            a, b = c.get(k), p.get(k)
            lines.append(f"| {k} | {fmt(a,'position')} / {fmt(b,'position')} | {fmt(a,'impressions')} / {fmt(b,'impressions')} | {fmt(a,'clicks')} / {fmt(b,'clicks')} |")
    quick = [r for r in cur if 8 <= r["position"] <= 20 and r["impressions"] >= 3]
    lines += ["", "## Quick wins (position 8–20, last 7 days)", ""]
    lines += [f"- {r['keys'][0]}: position {round(r['position'],1)}, {int(r['impressions'])} impressions"
              for r in sorted(quick, key=lambda r: -r["impressions"])[:15]] or ["- none"]
    lines += ["", f"Totals last 7 days: {int(sum(r['clicks'] for r in cur))} clicks, "
              f"{int(sum(r['impressions'] for r in cur))} impressions."]
    open(os.path.join(out_dir, "latest", "summary.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out"))
