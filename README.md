# dataiku-mcp

A local MCP server that exposes Dataiku DSS to Claude Code, built directly on
Dataiku's official `dataiku-api-client`. No third-party package holds the API key.

## Scope

Chosen deliberately — read access plus recipe/settings editing.

**Read**

| Tool | What it returns |
|---|---|
| `dss_instance_info` | DSS version; use to confirm connectivity |
| `dss_list_projects` | project keys visible to the API key |
| `dss_get_project` | metadata, summary, permissions |
| `dss_list_datasets` | dataset names, types, connections |
| `dss_get_dataset` | schema, params, partitioning |
| `dss_list_recipes` | recipes with inputs/outputs |
| `dss_get_recipe` | full definition + payload (code/config) |
| `dss_list_scenarios` | scenarios and whether active |
| `dss_get_scenario_runs` | recent run outcomes and timing |
| `dss_get_scenario_run_details` | per-step detail for one run |
| `dss_list_jobs` | recent build jobs and state |
| `dss_get_job_log` | job log (tail-truncated at 60k chars) |
| `dss_get_flow` | flow graph |
| `dss_get_project_settings` | raw project settings |

**Write** — gated behind `DATAIKU_ALLOW_WRITE`

| Tool | Effect |
|---|---|
| `dss_update_recipe_payload` | replaces a recipe's code/config |
| `dss_update_recipe_settings` | shallow-merges into recipe definition |
| `dss_update_project_settings` | shallow-merges into project settings |

**Not exposed, on purpose:** dataset row reads (keeps production data out of
chat context), scenario/job triggering, and deletes of any kind. If you need one
later, add it explicitly rather than reaching for a broader client.

## Setup

Built and tested on Windows with PowerShell; commands below are PowerShell,
with the macOS/Linux equivalent noted alongside.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "mcp[cli]" dataiku-api-client
```

(macOS/Linux: `python3 -m venv .venv` then
`./.venv/bin/python -m pip install "mcp[cli]" dataiku-api-client`)

## Credentials

The server reads these from its env block and never accepts them as tool
arguments:

- `DATAIKU_URL` — e.g. `https://dss.example.org` (include the port if non-standard)
- `DATAIKU_API_KEY` — a **personal** API key from DSS: your avatar → *Profile &
  settings* → *API keys*. Scope it to the projects you actually need.
- `DATAIKU_ALLOW_WRITE` — `true` to enable the three write tools; omit for read-only
- `DATAIKU_NO_CHECK_CERTIFICATE` — `true` only if the instance uses a self-signed cert

Keep the key out of anything that gets committed. If this directory ever becomes
a git repo, the key lives in `.mcp.json` — add it to `.gitignore` first.

## Smoke test

```powershell
$env:DATAIKU_URL="https://your-dss"; $env:DATAIKU_API_KEY="..."
.\.venv\Scripts\python.exe smoke_test.py
```

(macOS/Linux: `export DATAIKU_URL="https://your-dss" DATAIKU_API_KEY="..."` then
`./.venv/bin/python smoke_test.py`)

Checks connectivity, prints the DSS version and visible project count, and
reports whether the key has write permission — without changing anything.
