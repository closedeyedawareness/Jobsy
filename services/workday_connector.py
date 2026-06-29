"""
workday_connector.py — Workday REST API connector for Jobsy.

Authentication: OAuth 2.0 with Integration System User (ISU).
Docs: https://community.workday.com/sites/default/files/file-hosting/restapi/

Credentials needed (from Workday tenant admin):
  - Tenant name     (e.g. acme_corp or acme_corp_preview)
  - Client ID       (from API Client in Workday)
  - Client Secret   (from API Client)
  - Refresh Token   (from ISU non-expiring token or API Client)
  - API version     (default v1)
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd
import requests

# ── Workday nested-JSON → Jobsy column mapping ────────────────────────────
# Each entry: (dot-path into worker JSON, Jobsy column name)
# Adjust paths for your Workday version / tenant configuration.
_WORKER_PATHS = [
    # Identity
    ("employeeID",                                           "EmployeeID"),
    ("workerSummary.primaryJob.workerJobData.jobPostingTitle","JobTitle"),
    ("workerSummary.primaryJob.workerJobData.jobTitle",      "JobTitle"),
    ("workerSummary.primaryJob.businessTitle",               "JobTitle"),
    # Name
    ("person.legalName.firstName",                           "FirstName"),
    ("person.legalNameData.firstName",                       "FirstName"),
    ("person.legalName.lastName",                            "LastName"),
    ("person.legalNameData.lastName",                        "LastName"),
    # Org
    ("workerSummary.primaryJob.supervisoryOrganization.name","Department"),
    ("workerSummary.primaryJob.organization.name",           "Department"),
    ("workerSummary.businessUnit.name",                      "BusinessUnit"),
    # Manager
    ("workerSummary.primaryJob.manager.employeeID",          "ManagerID"),
    ("workerSummary.primaryJob.managerReference.id",         "ManagerID"),
    # Location
    ("workerSummary.primaryJob.location.name",               "Location"),
    ("workerSummary.primaryWorkAddress.city",                "Location"),
    # HR fields
    ("workerSummary.primaryJob.workerType.descriptor",       "ContractType"),
    ("workerSummary.primaryJob.scheduledWeeklyHours",        "FTE"),
]


def _get_path(obj: dict, path: str):
    """Traverse a dot-path through nested dicts. Returns None if any key is missing."""
    parts = path.split(".")
    cur = obj
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


class WorkdayConnector:
    """Fetch and map worker data from Workday REST API."""

    TOKEN_URL  = "https://wd2-impl-services1.workday.com/ccx/oauth2/{tenant}/token"
    RAAS_URL   = "https://wd2-impl-services1.workday.com/ccx/service/{tenant}/{module}/{version}"
    API_BASE   = "https://wd2-impl-services1.workday.com/ccx/api/{version}/{tenant}"

    def __init__(
        self,
        tenant: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        api_version: str = "v1",
    ):
        self.tenant        = tenant.strip()
        self.client_id     = client_id.strip()
        self.client_secret = client_secret.strip()
        self.refresh_token = refresh_token.strip()
        self.api_version   = api_version
        self._access_token: Optional[str] = None
        self.session = requests.Session()

    def _authenticate(self) -> str:
        """Get or refresh an OAuth 2.0 access token."""
        if self._access_token:
            return self._access_token
        url = self.TOKEN_URL.format(tenant=self.tenant)
        resp = requests.post(url, data={
            "grant_type":    "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
        }, timeout=15)
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        self.session.headers.update({
            "Authorization": f"Bearer {self._access_token}",
            "Accept":        "application/json",
        })
        return self._access_token

    def test_connection(self) -> tuple[bool, str]:
        """Attempt authentication and a lightweight workers call."""
        try:
            self._authenticate()
            base = self.API_BASE.format(version=self.api_version, tenant=self.tenant)
            r = self.session.get(f"{base}/workers?limit=1", timeout=15)
            if r.status_code == 200:
                return True, "Connected"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            return False, str(exc)

    def fetch_workers(
        self,
        limit: int = 100,
        offset: int = 0,
        extra_paths: Optional[list[tuple[str, str]]] = None,
    ) -> pd.DataFrame:
        """
        Fetch all workers and return a Jobsy-formatted DataFrame.

        limit / offset : pagination per page (Workday default max 100)
        extra_paths    : additional (dot_path, jobsy_column) tuples for custom fields
        """
        self._authenticate()
        base  = self.API_BASE.format(version=self.api_version, tenant=self.tenant)
        paths = list(_WORKER_PATHS) + (extra_paths or [])
        all_workers: list[dict] = []
        cur_offset = offset

        while True:
            r = self.session.get(
                f"{base}/workers",
                params={"limit": limit, "offset": cur_offset},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            batch = data.get("data", [])
            if not batch:
                break
            all_workers.extend(batch)
            total = data.get("total", 0)
            cur_offset += limit
            if cur_offset >= total:
                break

        if not all_workers:
            return pd.DataFrame()

        return self._map_to_jobsy(all_workers, paths)

    def fetch_workers_raas(
        self,
        report_name: str,
        module: str = "Human_Resources",
        version: str = "v38.0",
    ) -> pd.DataFrame:
        """
        Alternative: pull from a Workday Custom Report (RaaS — Reports as a Service).
        Useful if the standard REST endpoint doesn't return the fields you need.

        report_name : the report name configured by your Workday admin
        """
        self._authenticate()
        url = (f"https://wd2-impl-services1.workday.com/ccx/service/customreport2/"
               f"{self.tenant}/{report_name}?format=json")
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        rows = data.get("Report_Entry", [])
        if not rows:
            return pd.DataFrame()
        # RaaS returns flat dicts — apply basic mapping
        df = pd.DataFrame(rows)
        df.columns = [c.strip() for c in df.columns]
        rename = {
            "Employee_ID": "EmployeeID", "First_Name": "FirstName",
            "Last_Name": "LastName", "Job_Title": "JobTitle",
            "Department": "Department", "Manager_ID": "ManagerID",
            "Annual_Salary": "AnnualSalaryEUR", "Location": "Location",
        }
        df.rename(columns={k:v for k,v in rename.items() if k in df.columns}, inplace=True)
        return df

    def _map_to_jobsy(self, workers: list[dict], paths: list[tuple]) -> pd.DataFrame:
        rows = []
        for w in workers:
            out: dict = {"EmployeeID": w.get("id","") or w.get("employeeID","")}
            for path, col in paths:
                val = _get_path(w, path)
                if val is not None and col not in out:
                    out[col] = val
            rows.append(out)

        df = pd.DataFrame(rows)
        if "AnnualSalaryEUR" in df.columns:
            df["AnnualSalaryEUR"] = pd.to_numeric(df["AnnualSalaryEUR"], errors="coerce")
        for col in ("EmployeeID", "ManagerID"):
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df
