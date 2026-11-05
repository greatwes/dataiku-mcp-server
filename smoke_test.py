"""Verify DSS connectivity and report what the API key can reach.

Read-only: lists projects and inspects permissions. Changes nothing.
"""

import os
import sys

import dataikuapi


def main() -> int:
    url = os.environ.get("DATAIKU_URL", "").strip()
    key = os.environ.get("DATAIKU_API_KEY", "").strip()
    if not url or not key:
        print("Set DATAIKU_URL and DATAIKU_API_KEY first.", file=sys.stderr)
        return 2

    client = dataikuapi.DSSClient(url, key)
    if os.environ.get("DATAIKU_NO_CHECK_CERTIFICATE", "").lower() in ("1", "true", "yes"):
        client._session.verify = False

    info = client.get_instance_info()
    print(f"connected      : {url}")
    print(f"DSS version    : {info.raw.get('dssVersion')}")
    print(f"node type      : {info.raw.get('nodeType')}")

    projects = client.list_projects()
    print(f"projects visible: {len(projects)}")
    for p in projects[:15]:
        print(f"  - {p.get('projectKey')}  ({p.get('name')})")
    if len(projects) > 15:
        print(f"  ... and {len(projects) - 15} more")

    writes = os.environ.get("DATAIKU_ALLOW_WRITE", "").lower() in ("1", "true", "yes")
    print(f"write tools    : {'ENABLED' if writes else 'disabled'}")

    if projects:
        pk = projects[0].get("projectKey")
        perms = client.get_project(pk).get_permissions()
        print(f"perms on {pk}: owner={perms.get('owner')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
