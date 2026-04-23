# ClearCase → GitHub Migration — How to Run

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.9+ | `python3 --version` |
| `cleartool` on PATH | Must be on a machine with ClearCase client installed |
| `git` 2.20+ | `git --version` |
| `git-lfs` | Only needed if `use_lfs: true` in config |
| ClearCase view | Snapshot or dynamic view must already exist |
| GitHub token | Needs `repo` + `admin:org` scopes |

---

## Step 1 — Install Python dependencies

```bash
cd /home/ramram/Desktop/Personal/Clearcase_Git

python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

> `chardet` is optional but strongly recommended — it detects ISO-8859-1 / Windows-1252
> encodings in legacy C files and normalizes them to UTF-8 automatically.

---

## Step 2 — Create a ClearCase view (if you don't have one)

```bash
# Snapshot view (recommended for migration — no network dependency per file access)
cleartool mkview -snapshot -vws /net/cc_server/views/migration_view.vws \
    -tag migration_view /local/migration_view

# Set the config spec to select all branches
cleartool setcs -tag migration_view -current
```

---

## Step 3 — Edit `config.yaml`

Open [config.yaml](config.yaml) and set at minimum:

```yaml
clearcase:
  vob_tags:
    - /vobs/your_project      # adjust to your actual VOB path
  view_tag: migration_view    # the view you created above
  view_root: /view            # mount point on this machine

git:
  output_dir: ./git_output    # where the new git repo will be written

github:
  enabled: true
  org: your-github-org        # or leave empty for personal account
  repo_name: your_project_migrated
  token_env_var: GITHUB_TOKEN
  visibility: private
```

### Multiple VOBs

```yaml
clearcase:
  vob_tags:
    - /vobs/project_core
    - /vobs/project_libs
    - /vobs/project_tests
```

### UCM (streams / activities)

```yaml
clearcase:
  is_ucm: true
  stream_tag: integration_stream@/vobs/your_project
  baseline_tag: BL_RELEASE_3_0@/vobs/your_project
```

### Filter specific branches

```yaml
clearcase:
  include_branches:
    - main
    - rel3_bugfix
    - feature_xyz
  exclude_branches:
    - CHECKEDOUT
    - scratch_personal
```

---

## Step 4 — Create `authors.csv` (optional but recommended)

Map ClearCase usernames to Git `Name <email>` format.
Users not in the file get `username <username@migrated.local>` as a fallback.

```csv
# cc_username,Git Full Name,git@email.com
jsmith,John Smith,john.smith@company.com
mary.jones,Mary Jones,mary.jones@company.com
build_svc,Build Service,devops@company.com
```

---

## Step 5 — Set your GitHub token

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The token needs these scopes:
- `repo` (full control of private repositories)
- `admin:org` → `write:org` (if pushing to an org)

Create one at: **GitHub → Settings → Developer settings → Personal access tokens**

---

## Step 6 — Dry run (validate config, no changes made)

Always do a dry run first. It parses everything and prints the plan without
writing any git history or touching GitHub.

```bash
python3 main.py --config config.yaml --dry-run
```

Check `logs/migration.log` for warnings before proceeding.

---

## Step 7 — Full migration run

```bash
python3 main.py --config config.yaml
```

The pipeline runs 5 stages in sequence. Progress is printed to stdout and
logged to `logs/migration.log`.

### What gets written where

```
workspace/
  discovery.json          ← VOB structure (branches, labels, elements)
  commits.json            ← grouped commit plan
  enriched_commits.json   ← commits with file content (base64)
  version_cache/          ← per-version content cache (speeds up resume)
  lfs_objects/            ← LFS blob storage

git_output/               ← the finished git repository
  .git/
  .gitattributes
  .gitignore
  <your source files>

logs/
  migration.log           ← full pipeline log
  c_file_issues.md        ← report of all C file rewrites / warnings
  upload_lfs.sh           ← run this after push to upload LFS objects
```

---

## Step 8 — Resume after interruption

The pipeline saves state after each stage. If it crashes or you stop it:

```bash
# Resume from wherever it left off (default behaviour)
python3 main.py --config config.yaml

# Force restart from a specific stage
python3 main.py --config config.yaml --skip-to history
python3 main.py --config config.yaml --skip-to extract
python3 main.py --config config.yaml --skip-to convert
python3 main.py --config config.yaml --skip-to publish

# Start completely fresh (deletes saved state)
python3 main.py --config config.yaml --no-resume
```

---

## Step 9 — Review the C file issue report

After the run, open `logs/c_file_issues.md`. It lists every C/C++/Makefile
that was automatically rewritten and why:

| Issue kind | What was fixed |
|---|---|
| `cc_keywords` | `$Header: /vobs/...@@/main/5 $` → `$Header$` |
| `cc_include_ext` | `#include "foo.h@@/main/3"` → `#include "foo.h"` |
| `view_root_path` | `/view/myview/vobs/proj/` → `/vobs/proj/` |
| `makefile_cc_var` | `$(CLEARCASE_ROOT)` → `$(REPO_ROOT)` |
| `merge_conflict` | Flagged — manual review required |
| `derived_object` | Compiled object found in VOB — skipped |
| `pragma_ident` | `#pragma ident` with CC version — preserved |

Files with `merge_conflict` warnings need manual resolution before the
migrated repo can build cleanly.

---

## Step 10 — Push LFS objects (if LFS is enabled)

After `git push` completes, run the generated upload script:

```bash
cd git_output
bash ../logs/upload_lfs.sh
```

---

## Troubleshooting

### `cleartool not found`
The tool must run on a machine with the ClearCase client installed.
Copy the entire `Clearcase_Git/` folder to that machine and run there.

### `Permission denied` on `cleartool get`
Your view may not have the element checked in or the config spec may not
select the correct version. Check with:
```bash
cleartool ls /vobs/your_project/path/to/file.c
```

### Large VOB — history takes hours
Normal. Use `--skip-to extract` or `--skip-to convert` to resume after
the history stage completes. The `workspace/version_cache/` directory
caches extracted file content so re-runs are fast.

### `git fast-import` error: `fatal: Corrupt patch`
Usually caused by a file with a null byte that slipped through binary
detection. Set `skip_derived_objects: true` in `config.yaml` and re-run
with `--skip-to convert --no-resume` (extraction cache is still valid).

### GitHub 422 on repo creation
The repo already exists with that name. Either:
- Delete it on GitHub and re-run, or
- Set `push_force: true` in `config.yaml` to overwrite

### Encoding errors in C files
Install `chardet`: `pip install chardet`
This gives accurate detection of ISO-8859-1 / Windows-1252 / Shift-JIS
encoded legacy source files. Without it, latin-1 is used as fallback.

---

## Verifying the migrated repo

```bash
cd git_output

# Check all branches migrated
git branch -a

# Check all tags (ClearCase labels)
git tag | head -20

# Verify commit count
git log --oneline | wc -l

# Diff a specific file against the original ClearCase version
git show HEAD:src/main.c | diff - /view/migration_view/vobs/your_project/src/main.c
```

---

## Quick reference

```bash
# Minimal run (after editing config.yaml and setting GITHUB_TOKEN)
source venv/bin/activate
export GITHUB_TOKEN=ghp_...
python3 main.py --config config.yaml --dry-run   # validate first
python3 main.py --config config.yaml             # actual migration
```
