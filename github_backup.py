#!/usr/bin/env python3
"""Backup all repos for a single GitHub user/org.

Usage:
  GITHUB_TOKEN=... python github_backup.py --user USER --out /path/to/backup [--include-wikis]
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
    parser.add_argument("--user", required=True, help="GitHub username or org")
    parser.add_argument("--out", required=True, help="Backup destination directory")
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


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Missing GITHUB_TOKEN in environment.", file=sys.stderr)
        return 1

    timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    base_out = os.path.abspath(os.path.expanduser(args.out))
    backup_root = os.path.join(base_out, f"github_backup_{args.user}_{timestamp}")
    repos_dir = os.path.join(backup_root, "repos")
    meta_dir = os.path.join(backup_root, "metadata")
    os.makedirs(repos_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)

    # Pull all repos visible to the token and filter to the requested owner.
    repos = api_get_all("https://api.github.com/user/repos?per_page=100&affiliation=owner", token)
    owned_repos = [r for r in repos if r.get("owner", {}).get("login", "").lower() == args.user.lower()]

    manifest = {
        "user": args.user,
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



