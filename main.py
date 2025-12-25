import requests
import pandas as pd
import argparse
import os
from base64 import b64encode
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt

# ---------------- CONFIG ----------------
ORGANIZATION = "YOUR_ORG_NAME"
PROJECT = "YOUR_PROJECT_NAME"

# Set via environment variable for safety
# export AZURE_DEVOPS_PAT=xxxx
PAT = os.getenv("AZURE_DEVOPS_PAT")
# --------------------------------------


def auth_header():
    if not PAT:
        raise RuntimeError("AZURE_DEVOPS_PAT environment variable not set")
    token = ":" + PAT
    encoded = b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Azure DevOps PR Review Analyzer"
    )
    parser.add_argument("--repos", nargs="+", required=True)
    parser.add_argument("--reviewers", nargs="+", required=True)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument(
        "--date-mode",
        choices=["creation", "review"],
        default="review",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    return parser.parse_args()


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", ""))
    except ValueError:
        return None


def date_in_range(date, start, end):
    if not date:
        return False
    return start <= date.strftime("%Y-%m-%d") <= end


def get_repo_map(repo_names):
    url = (
        f"https://dev.azure.com/{ORGANIZATION}/{PROJECT}"
        f"/_apis/git/repositories?api-version=7.0"
    )
    repos = requests.get(url, headers=auth_header()).json()["value"]

    repo_map = {
        repo["name"]: repo["id"]
        for repo in repos
        if repo["name"] in repo_names
    }

    if not repo_map:
        raise RuntimeError("No matching repositories found")

    return repo_map


def get_all_prs(repo_id):
    all_prs, skip, top = [], 0, 100
    while True:
        url = (
            f"https://dev.azure.com/{ORGANIZATION}/{PROJECT}"
            f"/_apis/git/repositories/{repo_id}/pullrequests"
            f"?searchCriteria.status=all"
            f"&$top={top}&$skip={skip}&api-version=7.0"
        )
        response = requests.get(url, headers=auth_header())
        response.raise_for_status()
        batch = response.json().get("value", [])
        all_prs.extend(batch)
        if len(batch) < top:
            break
        skip += top
    return all_prs


def main():
    args = parse_args()
    reviewers = [r.lower() for r in args.reviewers]

    repo_map = get_repo_map(args.repos)

    rows = []
    raw_rows = []
    reviewer_summary = defaultdict(lambda: {"Approved": 0, "Rejected": 0})
    debug_stats = defaultdict(int)

    for repo_name, repo_id in repo_map.items():
        prs = get_all_prs(repo_id)
        debug_stats["total_prs"] += len(prs)

        for pr in prs:
            for reviewer in pr.get("reviewers", []):
                debug_stats["total_reviewer_entries"] += 1

                email = reviewer.get("uniqueName", "").lower()
                vote = reviewer.get("vote", 0)

                raw_rows.append({
                    "Repository": repo_name,
                    "PR ID": pr["pullRequestId"],
                    "Reviewer": email,
                    "Vote": vote,
                    "Reviewed Date": reviewer.get("reviewedDate"),
                    "PR Created Date": pr.get("creationDate"),
                })

                if email not in reviewers:
                    debug_stats["filtered_reviewer"] += 1
                    continue

                if vote not in (10, 5, -10):
                    debug_stats["filtered_vote"] += 1
                    continue

                decision = "Approved" if vote > 0 else "Rejected"

                check_date = (
                    parse_date(pr.get("creationDate"))
                    if args.date_mode == "creation"
                    else parse_date(
                        reviewer.get("reviewedDate", pr.get("creationDate"))
                    )
                )

                if not date_in_range(check_date, args.start, args.end):
                    debug_stats["filtered_date"] += 1
                    continue

                reviewer_summary[email][decision] += 1
                debug_stats["rows_added"] += 1

                rows.append({
                    "Repository": repo_name,
                    "PR ID": pr["pullRequestId"],
                    "Title": pr["title"],
                    "Reviewer": email,
                    "Decision": decision,
                    "Decision Date": check_date,
                    "PR Created Date": pr.get("creationDate"),
                    "Created By": pr["createdBy"]["displayName"],
                    "Month": check_date.strftime("%Y-%m"),
                })

    if args.debug:
        print("\n🐞 DEBUG STATS")
        print("=" * 50)
        for k, v in debug_stats.items():
            print(f"{k:25}: {v}")

    if not rows:
        print("\n⚠️ No PR review data matched the given filters.")
        print("Excel file will NOT be generated.")
        return

    df = pd.DataFrame(rows)
    raw_df = pd.DataFrame(raw_rows)

    monthly = (
        df.groupby(["Month", "Decision"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    reviewer_df = (
        pd.DataFrame.from_dict(reviewer_summary, orient="index")
        .reset_index()
        .rename(columns={"index": "Reviewer"})
    )

    output_dir = Path(__file__).parent
    excel_path = output_dir / "reviewed_prs_report.xlsx"

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All PRs", index=False)
        monthly.to_excel(writer, sheet_name="Monthly Summary", index=False)
        reviewer_df.to_excel(writer, sheet_name="Reviewer Summary", index=False)
        raw_df.to_excel(writer, sheet_name="Raw API Data", index=False)

    daily = (
        df.groupby([df["Decision Date"].dt.date, "Decision"])
        .size()
        .unstack(fill_value=0)
    )

    if not daily.empty:
        graph_path = output_dir / "daily_approval_graph.png"
        daily.plot(kind="bar", figsize=(12, 6))
        plt.title("Per-Day PR Approvals / Rejections")
        plt.xlabel("Date")
        plt.ylabel("Count")
        plt.tight_layout()
        plt.savefig(graph_path)
        plt.close()
        print(f"📈 Daily graph saved: {graph_path}")

    print("\n📊 REVIEW SUMMARY")
    print("=" * 50)
    print(reviewer_df)
    print(f"\n📄 Excel report saved at: {excel_path}")


if __name__ == "__main__":
    main()
