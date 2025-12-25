"""
Azure DevOps PR Review Analyzer

Fetch Pull Requests reviewed (approved/rejected) by given reviewers
across multiple repositories, with date filtering, Excel reports,
and visual analytics.

NOTE:
- This script is safe for public repositories.
- Insert your PAT locally before running.
"""

import requests
import pandas as pd
import argparse
from base64 import b64encode
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt

# ---------------- CONFIG ----------------
ORGANIZATION = "YOUR_ORG_NAME"
PROJECT = "YOUR_PROJECT_NAME"
PAT = "YOUR_AZURE_DEVOPS_PAT"
# --------------------------------------


def auth_header():
    token = ":" + PAT
    encoded = b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def parse_args():
    parser = argparse.ArgumentParser(description="Azure DevOps PR Review Analyzer")
    parser.add_argument("--repos", nargs="+", required=True)
    parser.add_argument("--reviewers", nargs="+", required=True)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--date-mode", choices=["creation", "review"], default="review")
    return parser.parse_args()


def parse_date(date_str):
    return datetime.fromisoformat(date_str.replace("Z", ""))


def date_in_range(date, start, end):
    return start <= date.strftime("%Y-%m-%d") <= end


def get_repo_map(repo_names):
    url = f"https://dev.azure.com/{ORGANIZATION}/{PROJECT}/_apis/git/repositories?api-version=7.0"
    repos = requests.get(url, headers=auth_header()).json()["value"]

    return {
        repo["name"]: repo["id"]
        for repo in repos
        if repo["name"] in repo_names
    }


def get_all_prs(repo_id):
    all_prs, skip, top = [], 0, 100
    while True:
        url = (
            f"https://dev.azure.com/{ORGANIZATION}/{PROJECT}"
            f"/_apis/git/repositories/{repo_id}/pullrequests"
            f"?searchCriteria.status=all&$top={top}&$skip={skip}&api-version=7.0"
        )
        batch = requests.get(url, headers=auth_header()).json()["value"]
        all_prs.extend(batch)
        if len(batch) < top:
            break
        skip += top
    return all_prs


def main():
    args = parse_args()
    repo_map = get_repo_map(args.repos)

    rows = []
    reviewer_summary = defaultdict(lambda: {"Approved": 0, "Rejected": 0})

    for repo_name, repo_id in repo_map.items():
        for pr in get_all_prs(repo_id):
            for reviewer in pr.get("reviewers", []):
                email = reviewer.get("uniqueName", "").lower()
                if email not in [r.lower() for r in args.reviewers]:
                    continue

                vote = reviewer.get("vote", 0)
                if vote not in (10, 5, -10):
                    continue

                decision = "Approved" if vote > 0 else "Rejected"
                check_date = (
                    parse_date(pr["creationDate"])
                    if args.date_mode == "creation"
                    else parse_date(reviewer.get("reviewedDate", pr["creationDate"]))
                )

                if not date_in_range(check_date, args.start, args.end):
                    continue

                reviewer_summary[email][decision] += 1

                rows.append({
                    "Repository": repo_name,
                    "PR ID": pr["pullRequestId"],
                    "Title": pr["title"],
                    "Reviewer": email,
                    "Decision": decision,
                    "Decision Date": reviewer.get("reviewedDate"),
                    "PR Created Date": pr["creationDate"],
                    "Created By": pr["createdBy"]["displayName"],
                    "Month": check_date.strftime("%Y-%m"),
                })

    df = pd.DataFrame(rows)

    output_dir = Path(__file__).parent
    excel_path = output_dir / "reviewed_prs_report.xlsx"

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All PRs", index=False)

    print(f"Report generated: {excel_path}")


if __name__ == "__main__":
    main()
