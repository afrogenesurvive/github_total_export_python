# GitHub Backup Script

A Python script to create a full backup of all repositories (including metadata) for a GitHub user or organisation. Each backup is self-contained with a timestamped directory, mirror clones of every repository, and exported metadata such as issues, pull requests, and releases.

---

## Features

- **Mirror clones** — each repo is cloned with `--mirror`, preserving all branches, tags, and refs.
- **Metadata backup** — exports issues, pull requests, and releases as readable JSON files.
- **Wiki support** — optionally backs up repository wikis (if they exist).
- **Incremental** — re-run the script and existing mirror directories are updated with `git remote update --prune`.
- **Pagination safe** — automatically fetches all pages from the GitHub API.
- **Manifest file** — a `manifest.json` is generated listing every backed-up repo and its location.

---

## Prerequisites

- **Python 3.7+**
- **Git** installed and available in your `PATH`
- A **GitHub personal access token** with the following scopes:
  - `repo` (for private repositories)
  - `public_repo` (for public repositories only)

> Create a token at: https://github.com/settings/tokens

---

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/github_total_export_python.git
cd github_total_export_python

# (Optional) Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate
```

No external Python packages are required — the script uses only the standard library.

---

## Usage

### Basic backup (public repos owned by a user)

```bash
GITHUB_TOKEN=ghp_your_token_here python github_backup.py --user octocat --out /path/to/backup
```

### Include wikis

```bash
GITHUB_TOKEN=ghp_your_token_here python github_backup.py --user octocat --out /path/to/backup --include-wikis
```

### Backup an organisation's repos

```bash
GITHUB_TOKEN=ghp_your_token_here python github_backup.py --user my-org --out /path/to/backup
```

---

## Arguments

| Argument          | Required | Description                                          |
| ----------------- | -------- | ---------------------------------------------------- |
| `--user`          | Yes      | GitHub username or organisation name to back up      |
| `--out`           | Yes      | Destination directory for the backup                 |
| `--include-wikis` | No       | Also clone wikis for each repository (if they exist) |

The token is passed through the environment variable `GITHUB_TOKEN`.

---

## Output Structure

```
/path/to/backup/
└── github_backup_<user>_<timestamp>/
    ├── manifest.json              # Overview of all backed-up repos
    ├── repos/
    │   ├── repo-a.git/            # Mirror clone of repo-a
    │   ├── repo-b.git/            # Mirror clone of repo-b
    │   └── repo-a.wiki.git/       # Wiki mirror (if --include-wikis)
    └── metadata/
        ├── repo-a/
        │   ├── repo.json          # Full repository metadata from GitHub API
        │   ├── issues.json        # All issues (open & closed)
        │   ├── pulls.json         # All pull requests (open & closed)
        │   └── releases.json      # All releases
        └── repo-b/
            ├── repo.json
            ├── issues.json
            ├── pulls.json
            └── releases.json
```

### `manifest.json` structure

```json
{
  "user": "octocat",
  "timestamp_utc": "20260514T120000Z",
  "repo_count": 2,
  "repos": [
    {
      "name": "repo-a",
      "full_name": "octocat/repo-a",
      "mirror_path": "/path/.../repos/repo-a.git",
      "metadata_path": "/path/.../metadata/repo-a"
    }
  ]
}
```

---

## Restoring a Repository

Because the script uses `--mirror` clones, restoring a repository is straightforward:

```bash
# Create a working copy from the mirror
git clone /path/to/backup/repos/repo-a.git my-repo-a
```

Or push the mirror to a new remote:

```bash
cd /path/to/backup/repos/repo-a.git
git remote add new-origin https://github.com/YOU/new-repo.git
git push --mirror new-origin
```

---

## Notes

- **Incremental runs**: Running the same command again updates existing mirror clones incrementally rather than re-cloning.
- **Token scope**: Only repositories the token has access to will be backed up. Private repos require a token with the `repo` scope.
- **Rate limiting**: The script uses an unauthenticated-like API access pattern (no `requests` library) but is authenticated via the token, giving you a higher rate limit (5 000 requests/hour).
- **Organisations**: Pass the organisation name as `--user`. The script filters repos to only those owned by the specified user or org.

---

## Troubleshooting

| Problem                     | Likely cause                                    |
| --------------------------- | ----------------------------------------------- |
| `Missing GITHUB_TOKEN`      | Token not set in the environment                |
| `403` or `Not Found` errors | Token lacks required scopes or is expired       |
| No repos backed up          | Token doesn't have access, or `--user` is wrong |
| Wiki cloning fails          | The repo has no wiki — this is silently skipped |

---

## Disclaimer

This tool is not affiliated with or endorsed by GitHub, Inc. Use it responsibly and in accordance with GitHub's Terms of Service.
