# Azure DevOps PR Review Analyzer
A python CLI tool to analyze Azure DevOps Pull Request reviews across multiple repositories and reviewers with Excel reports, graphs and audit/debug support.

## Features
- Multi-repository & multi-reviewer support
- Date filtering (creation or review date)
- Pagination-safe Azure DevOps API usage
- Excel report with multiple sheets
- Daily approval/rejection graph
- Debug & audit mode with raw API data

## Setup
```bash
pip install -r requirements.txt
set AZURE_DEVOPS_PAT=your_pat_here
```

## Usage
```bash
python main.py   --repos Repo1 Repo2   --reviewers user1@company.com user2@company.com   --from 2025-01-01   --to 2025-01-31   --date-mode review   --debug
```

## Output
- reviewed_prs_report.xlsx
- daily_approval_graph.png
