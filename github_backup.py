#!/usr/bin/env python3
"""Backup all repos for a single GitHub user/org.

Usage:
  python3 github_backup.py --out /path/to/backup [--user USER] [--config PATH] [--include-wikis]

Settings are read from an optional .env file (KEY=VALUE format) in the current
working directory or next to this script, or from the process environment:
  GITHUB_TOKEN   GitHub personal access token (required)
  GITHUB_USER    GitHub username or org (used unless --user is passed)

Repo selection comes from the GITHUB_REPOS environment variable (comma-separated,
loaded from .env), or from a JSON config file (see --config / config.json):
  GITHUB_REPOS=repo-a,repo-b          back up only these repos
  empty GITHUB_REPOS / {"repos": []}  back up all owned repos
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup GitHub repos and metadata")
    parser.add_argument("--user", help="GitHub username or org (defaults to GITHUB_USER from .env)")
    parser.add_argument("--out", required=True, help="Backup destination directory")
    parser.add_argument("--config", help="Path to a JSON config file (default: config.json if present)")
    parser.add_argument("--include-wikis", action="store_true", help="Clone repo wikis if they exist")
    return parser.parse_args()


def api_request(url: str, token: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        link = resp.headers.get("Link")

    next_url = None
    if link:
        for part in link.split(","):
            m = re.search(r"<([^>]+)>; rel=\"([^\"]+)\"", part.strip())
            if m and m.group(2) == "next":
                next_url = m.group(1)
                break

    if isinstance(data, list):
        return data, next_url
    return [data], next_url


def api_get_all(url: str, token: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    next_url: Optional[str] = url
    while next_url:
        page_items, next_url = api_request(next_url, token)
        items.extend(page_items)
    return items


def run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def repo_mirror(repo_clone_url: str, mirror_path: str) -> None:
    if os.path.isdir(mirror_path):
        run(["git", "-C", mirror_path, "remote", "update", "--prune"])
        return
    run(["git", "clone", "--mirror", repo_clone_url, mirror_path])


def clone_wiki(repo_clone_url: str, wiki_path: str) -> None:
    wiki_url = repo_clone_url.replace(".git", ".wiki.git")
    # Only clone if wiki exists.
    try:
        run(["git", "ls-remote", "--heads", wiki_url])
    except subprocess.CalledProcessError:
        return
    if os.path.isdir(wiki_path):
        run(["git", "-C", wiki_path, "fetch", "--all", "--prune"])
        return
    run(["git", "clone", "--mirror", wiki_url, wiki_path])


def write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def load_dotenv(path: Optional[str] = None) -> None:
    """Load KEY=VALUE pairs from a .env file into the environment (stdlib only).

    Existing environment variables are never overwritten, so an explicitly set
    GITHUB_TOKEN still wins. Values wrapped in matching single/double quotes
    have the quotes stripped. Blank lines and lines starting with '#' are
    ignored.

    If no path is given, looks for '.env' in the current working directory and
    then next to this script.
    """
    if path is None:
        candidates = [os.path.join(os.getcwd(), ".env")]
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.abspath(script_dir) != os.path.abspath(os.getcwd()):
            candidates.append(os.path.join(script_dir, ".env"))
        path = next((c for c in candidates if os.path.isfile(c)), None)
    if not path or not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load backup options from a JSON config file.

    Supported keys:
      repos: list of repository names to back up. If empty or absent, all
             repos owned by the user are backed up.

    If no path is given, looks for 'config.json' in the current working
    directory and then next to this script. Returns {} if the file is absent.
    """
    if path is None:
        candidates = [os.path.join(os.getcwd(), "config.json")]
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.abspath(script_dir) != os.path.abspath(os.getcwd()):
            candidates.append(os.path.join(script_dir, "config.json"))
        path = next((c for c in candidates if os.path.isfile(c)), None)
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    args = parse_args()
    load_dotenv()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Missing GITHUB_TOKEN in environment.", file=sys.stderr)
        return 1

    user = args.user or os.environ.get("GITHUB_USER")
    if not user:
        print("Missing user. Pass --user or set GITHUB_USER in .env.", file=sys.stderr)
        return 1

    config = load_config(args.config)
    selected = config.get("repos") or []
    if not isinstance(selected, list):
        print("Config key 'repos' must be a list of repository names.", file=sys.stderr)
        return 1

    # GITHUB_REPOS (comma-separated, loaded from .env) overrides config.json.
    env_repos = os.environ.get("GITHUB_REPOS")
    if env_repos and env_repos.strip():
        selected = [r.strip() for r in env_repos.split(",") if r.strip()]

    timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    base_out = os.path.abspath(os.path.expanduser(args.out))
    backup_root = os.path.join(base_out, f"github_backup_{user}_{timestamp}")
    repos_dir = os.path.join(backup_root, "repos")
    meta_dir = os.path.join(backup_root, "metadata")
    os.makedirs(repos_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)

    # Pull all repos visible to the token and filter to the requested owner.
    repos = api_get_all("https://api.github.com/user/repos?per_page=100&affiliation=owner", token)
    owned_repos = [r for r in repos if r.get("owner", {}).get("login", "").lower() == user.lower()]

    # Restrict to the repos listed in the config file, if any.
    if selected:
        selected_set = set(selected)
        owned_repos = [r for r in owned_repos if r["name"] in selected_set]
        missing = sorted(selected_set - {r["name"] for r in owned_repos})
        if missing:
            print(f"Warning: no repo(s) found matching: {', '.join(missing)}", file=sys.stderr)

    manifest = {
        "user": user,
        "timestamp_utc": timestamp,
        "repo_count": len(owned_repos),
        "repos": [],
    }

    for repo in owned_repos:
        name = repo["name"]
        full_name = repo["full_name"]
        clone_url = repo["clone_url"]

        mirror_path = os.path.join(repos_dir, f"{name}.git")
        repo_mirror(clone_url, mirror_path)

        repo_meta_dir = os.path.join(meta_dir, name)
        write_json(os.path.join(repo_meta_dir, "repo.json"), repo)

        issues_url = f"https://api.github.com/repos/{full_name}/issues?state=all&per_page=100"
        pulls_url = f"https://api.github.com/repos/{full_name}/pulls?state=all&per_page=100"
        releases_url = f"https://api.github.com/repos/{full_name}/releases?per_page=100"

        issues = api_get_all(issues_url, token)
        pulls = api_get_all(pulls_url, token)
        releases = api_get_all(releases_url, token)

        write_json(os.path.join(repo_meta_dir, "issues.json"), issues)
        write_json(os.path.join(repo_meta_dir, "pulls.json"), pulls)
        write_json(os.path.join(repo_meta_dir, "releases.json"), releases)

        if args.include_wikis:
            wiki_path = os.path.join(repos_dir, f"{name}.wiki.git")
            clone_wiki(clone_url, wiki_path)

        manifest["repos"].append({
            "name": name,
            "full_name": full_name,
            "mirror_path": mirror_path,
            "metadata_path": repo_meta_dir,
        })

    write_json(os.path.join(backup_root, "manifest.json"), manifest)

    print(f"Backup complete: {backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



