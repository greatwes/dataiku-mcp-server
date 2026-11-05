"""MCP server exposing Dataiku DSS to Claude over the official dataiku-api-client.

Scope is deliberately narrow:
  - read: projects, datasets/schemas, recipes, scenarios, jobs, flow
  - write: recipe payloads/settings and project settings ONLY

Explicitly NOT exposed: dataset row reads, scenario/job triggering, and any
delete. Those were left out on purpose - adding a tool here widens what can
happen to production without anyone reviewing it.
"""

import json
import os
import sys
from typing import Any

import dataikuapi
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("dataiku")

MAX_CHARS = 60_000
_client = None


def _env(name: str, required: bool = True) -> str:
    val = os.environ.get(name, "").strip()
    if required and not val:
        raise RuntimeError(
            f"{name} is not set. Configure it in the MCP server env block; "
            "never pass credentials as tool arguments."
        )
    return val


def client():
    global _client
    if _client is None:
        c = dataikuapi.DSSClient(_env("DATAIKU_URL"), _env("DATAIKU_API_KEY"))
        if os.environ.get("DATAIKU_NO_CHECK_CERTIFICATE", "").lower() in ("1", "true", "yes"):
            c._session.verify = False
        _client = c
    return _client


def writes_allowed() -> bool:
    return os.environ.get("DATAIKU_ALLOW_WRITE", "").lower() in ("1", "true", "yes")


def require_write(what: str) -> None:
    if not writes_allowed():
        raise RuntimeError(
            f"Refusing to {what}: DATAIKU_ALLOW_WRITE is not enabled for this server. "
            "Set it in the MCP config env block to allow recipe/settings edits."
        )


def out(payload: Any) -> str:
    """Serialize, truncating rather than flooding the context window."""
    text = json.dumps(payload, indent=2, default=str)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n... [truncated at {MAX_CHARS} chars]"
    return text


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------

@mcp.tool()
def dss_instance_info() -> str:
    """DSS version and instance-level info. Use to confirm connectivity."""
    return out(client().get_instance_info().raw)


@mcp.tool()
def dss_list_projects() -> str:
    """List project keys and names visible to the configured API key."""
    return out([
        {"projectKey": p.get("projectKey"), "name": p.get("name"),
         "ownerLogin": p.get("ownerLogin")}
        for p in client().list_projects()
    ])


@mcp.tool()
def dss_get_project(project_key: str) -> str:
    """Metadata, summary and permissions for one project."""
    p = client().get_project(project_key)
    return out({
        "metadata": p.get_metadata(),
        "summary": p.get_summary(),
        "permissions": p.get_permissions(),
    })


@mcp.tool()
def dss_list_datasets(project_key: str) -> str:
    """List datasets in a project with type and connection - no row data."""
    return out([
        {"name": d.get("name"), "type": d.get("type"),
         "connection": d.get("params", {}).get("connection"),
         "tags": d.get("tags", [])}
        for d in client().get_project(project_key).list_datasets()
    ])


@mcp.tool()
def dss_get_dataset(project_key: str, dataset_name: str) -> str:
    """Schema, partitioning and settings for one dataset. Does not read rows."""
    settings = client().get_project(project_key).get_dataset(dataset_name).get_settings()
    raw = settings.get_raw()
    return out({
        "schema": raw.get("schema"),
        "params": raw.get("params"),
        "partitioning": raw.get("partitioning"),
    })


@mcp.tool()
def dss_list_recipes(project_key: str) -> str:
    """List recipes in a project with their inputs and outputs."""
    return out([
        {"name": r.get("name"), "type": r.get("type"),
         "inputs": r.get("inputs"), "outputs": r.get("outputs")}
        for r in client().get_project(project_key).list_recipes()
    ])


@mcp.tool()
def dss_get_recipe(project_key: str, recipe_name: str) -> str:
    """Full definition and payload (code/config) of one recipe."""
    settings = client().get_project(project_key).get_recipe(recipe_name).get_settings()
    return out({
        "recipe": settings.get_recipe_raw_definition(),
        "payload": settings.get_payload(),
    })


@mcp.tool()
def dss_list_scenarios(project_key: str) -> str:
    """List scenarios in a project, including whether each is active."""
    return out(client().get_project(project_key).list_scenarios())


@mcp.tool()
def dss_get_scenario_runs(project_key: str, scenario_id: str, limit: int = 10) -> str:
    """Recent run history for a scenario: outcome and timing.

    Read-only - this never starts a run.
    """
    runs = client().get_project(project_key).get_scenario(scenario_id).get_last_runs(limit=limit)
    return out([
        {"runId": r.run.get("runId"), "outcome": r.outcome,
         "start": r.run.get("start"), "end": r.run.get("end")}
        for r in runs
    ])


@mcp.tool()
def dss_get_scenario_run_details(project_key: str, scenario_id: str, run_id: str) -> str:
    """Per-step detail for one scenario run - use to locate which activity failed."""
    sc = client().get_project(project_key).get_scenario(scenario_id)
    for r in sc.get_last_runs(limit=50):
        if r.run.get("runId") == run_id:
            return out(r.get_details().details)
    raise RuntimeError(f"run {run_id} not found in the last 50 runs of {scenario_id}")


@mcp.tool()
def dss_list_jobs(project_key: str, limit: int = 20) -> str:
    """Recent build jobs for a project with their state."""
    jobs = client().get_project(project_key).list_jobs()[:limit]
    return out([
        {"jobId": j.get("def", {}).get("id"), "state": j.get("state"),
         "startTime": j.get("startTime"), "endTime": j.get("endTime")}
        for j in jobs
    ])


@mcp.tool()
def dss_get_job_log(project_key: str, job_id: str) -> str:
    """Full log for a build job. Truncated to the tail if very large."""
    log = client().get_project(project_key).get_job(job_id).get_log()
    if len(log) > MAX_CHARS:
        log = f"... [head truncated]\n{log[-MAX_CHARS:]}"
    return log


@mcp.tool()
def dss_get_flow(project_key: str) -> str:
    """The project flow graph - how datasets and recipes connect."""
    return out(client().get_project(project_key).get_flow().get_graph().data)


@mcp.tool()
def dss_get_project_settings(project_key: str) -> str:
    """Raw project settings - read this before calling dss_update_project_settings."""
    return out(client().get_project(project_key).get_settings().get_raw())


# --------------------------------------------------------------------------
# Write - recipes and settings only, gated on DATAIKU_ALLOW_WRITE
# --------------------------------------------------------------------------

@mcp.tool()
def dss_update_recipe_payload(project_key: str, recipe_name: str, payload: str) -> str:
    """Replace a recipe's payload (its code or config) and save.

    Overwrites the whole payload - call dss_get_recipe first and edit that text.
    """
    require_write(f"edit recipe {project_key}.{recipe_name}")
    settings = client().get_project(project_key).get_recipe(recipe_name).get_settings()
    before = settings.get_payload() or ""
    settings.set_payload(payload)
    settings.save()
    return out({
        "saved": f"{project_key}.{recipe_name}",
        "charsBefore": len(before),
        "charsAfter": len(payload),
    })


@mcp.tool()
def dss_update_recipe_settings(project_key: str, recipe_name: str, updates_json: str) -> str:
    """Shallow-merge a JSON object into a recipe's raw definition and save.

    Only the top-level keys present in updates_json are touched.
    """
    require_write(f"edit settings of recipe {project_key}.{recipe_name}")
    updates = json.loads(updates_json)
    if not isinstance(updates, dict):
        raise ValueError("updates_json must be a JSON object")
    settings = client().get_project(project_key).get_recipe(recipe_name).get_settings()
    settings.get_recipe_raw_definition().update(updates)
    settings.save()
    return out({"saved": f"{project_key}.{recipe_name}", "keys": sorted(updates)})


@mcp.tool()
def dss_update_project_settings(project_key: str, updates_json: str) -> str:
    """Shallow-merge a JSON object into a project's settings and save.

    Only the top-level keys present in updates_json are touched. Settings such
    as the scenario concurrency cap are nested - read dss_get_project_settings
    first and merge the whole parent object.
    """
    require_write(f"edit settings of project {project_key}")
    updates = json.loads(updates_json)
    if not isinstance(updates, dict):
        raise ValueError("updates_json must be a JSON object")
    settings = client().get_project(project_key).get_settings()
    settings.get_raw().update(updates)
    settings.save()
    return out({"saved": project_key, "keys": sorted(updates)})


if __name__ == "__main__":
    try:
        mcp.run()
    except Exception as exc:  # surface config errors legibly in the MCP log
        print(f"dataiku-mcp failed: {exc}", file=sys.stderr)
        raise
