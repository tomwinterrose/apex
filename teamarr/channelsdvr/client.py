"""Channels DVR Server client for triggering M3U + XMLTV refresh.

Channels DVR exposes an unauthenticated REST API on port 8089
(see https://getchannels.com/docs/server-api/introduction/). The API
requires requests to originate from the same local network — Teamarr
deployments live next to the DVR, so no auth handling is needed here.

CDVR splits "channels" and "guide" into two providers, each with its
own refresh verb:

* ``POST /providers/m3u/sources/<source_name>/refresh`` — refreshes the
  M3U channel list. Returns ``200 OK`` with body ``true`` as soon as the
  request is accepted; the actual refresh runs in the background.
* ``PUT /dvr/lineups/<lineup_id>`` — refreshes the XMLTV lineup that
  CDVR creates alongside an M3U source with EPG. Without this call the
  channel list is fresh but the guide data is stale, which is the
  whole reason Teamarr triggers the hook.

Both endpoints are fire-and-forget — there is no completion event or
task-id to poll, so this client only reports whether each request was
accepted.
"""

import logging
import time
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class ChannelsDVRClient:
    """Client for Channels DVR Server API."""

    SERVER_LABEL: str = "CHANNELSDVR"

    def __init__(
        self,
        base_url: str,
        source_name: str = "",
        lineup_id: str = "",
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.source_name = source_name
        # CDVR names the XMLTV lineup of a custom M3U source "XMLTV-<source_name>"
        # (e.g. source "dispatcharr" → lineup "XMLTV-dispatcharr"). When no lineup
        # is explicitly configured, derive it from the source so the guide refresh
        # still fires — otherwise the channels refresh but the EPG silently doesn't.
        self.lineup_id = lineup_id or (f"XMLTV-{source_name}" if source_name else "")
        # True when lineup_id was derived rather than explicitly configured.
        self.lineup_derived = bool(not lineup_id and self.lineup_id)
        self.timeout = timeout

    def _source_path(self) -> str:
        return f"/providers/m3u/sources/{quote(self.source_name, safe='')}"

    def list_m3u_sources(self) -> dict:
        """Fetch the list of M3U sources configured on the server.

        Channels DVR has no list endpoint at /providers/m3u/sources; instead
        every tuner and provider surfaces under /devices, and M3U sources are
        the entries with Provider == "m3u". The FriendlyName field is the
        source name used in /providers/m3u/sources/<name>/refresh.

        Returns:
            dict with success, sources (list of source names), error
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/devices",
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            return {
                "success": False,
                "sources": [],
                "error": f"Cannot connect to {self.base_url}",
            }
        except httpx.HTTPError as e:
            return {"success": False, "sources": [], "error": str(e)}

        try:
            data = resp.json()
        except ValueError:
            return {
                "success": False,
                "sources": [],
                "error": "Devices endpoint did not return JSON",
            }

        sources: list[str] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                provider = item.get("Provider") or item.get("provider") or ""
                if str(provider).lower() != "m3u":
                    continue
                name = (
                    item.get("FriendlyName")
                    or item.get("friendlyName")
                    or item.get("Name")
                    or item.get("name")
                )
                if name:
                    sources.append(str(name))

        return {"success": True, "sources": sources}

    def test_connection(self) -> dict:
        """Verify connectivity, version, and that the source exists.

        Returns:
            dict with success, server_version, source_name, error
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/status",
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            return {
                "success": False,
                "error": f"Cannot connect to {self.base_url}",
            }
        except httpx.HTTPError as e:
            return {"success": False, "error": str(e)}

        server_version: str | None = None
        try:
            data = resp.json()
            server_version = data.get("version") if isinstance(data, dict) else None
        except ValueError:
            # /status returned non-JSON — still treat as reachable
            pass

        if not self.source_name:
            return {
                "success": True,
                "server_version": server_version,
                "source_name": None,
            }

        try:
            src_resp = httpx.get(
                f"{self.base_url}{self._source_path()}",
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            return {
                "success": False,
                "server_version": server_version,
                "error": f"Failed to verify source: {e}",
            }

        if src_resp.status_code == 404:
            return {
                "success": False,
                "server_version": server_version,
                "error": f"Source '{self.source_name}' not found on Channels DVR",
            }
        if src_resp.status_code >= 400:
            return {
                "success": False,
                "server_version": server_version,
                "error": f"Source check returned HTTP {src_resp.status_code}",
            }

        return {
            "success": True,
            "server_version": server_version,
            "source_name": self.source_name,
        }

    def trigger_m3u_refresh(self, timeout: int = 60) -> dict:
        """Trigger an M3U source refresh on the Channels DVR server.

        The endpoint returns immediately — Channels DVR runs the refresh
        in the background, so this method does not poll for completion.

        Returns:
            dict with success, message, duration
        """
        if not self.source_name:
            return {
                "success": False,
                "message": "No source name configured",
                "duration": 0,
            }

        start = time.monotonic()
        try:
            resp = httpx.post(
                f"{self.base_url}{self._source_path()}/refresh",
                timeout=timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            duration = time.monotonic() - start
            if e.response.status_code == 404:
                msg = f"Source '{self.source_name}' not found"
            else:
                msg = f"Refresh failed: HTTP {e.response.status_code}"
            return {"success": False, "message": msg, "duration": duration}
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"Refresh failed: {e}",
                "duration": time.monotonic() - start,
            }

        duration = time.monotonic() - start
        logger.info(
            "[%s] Triggered refresh for source '%s' in %.2fs",
            self.SERVER_LABEL,
            self.source_name,
            duration,
        )
        return {
            "success": True,
            "message": f"Refresh triggered for source '{self.source_name}'",
            "duration": duration,
        }

    def list_lineups(self) -> dict:
        """Fetch the list of XMLTV lineups configured on the server.

        ``GET /dvr/lineups`` returns every guide lineup CDVR knows about —
        Gracenote, XMLTV-from-M3U, and any user-imported XMLTV files. The
        ``ID`` field is what the refresh endpoint expects in the URL path.
        We surface ID + Name so the UI can show a user-friendly label
        while still POSTing the canonical ID.

        Returns:
            dict with success, lineups (list of {id, name}), error
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/dvr/lineups",
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            return {
                "success": False,
                "lineups": [],
                "error": f"Cannot connect to {self.base_url}",
            }
        except httpx.HTTPError as e:
            return {"success": False, "lineups": [], "error": str(e)}

        try:
            data = resp.json()
        except ValueError:
            return {
                "success": False,
                "lineups": [],
                "error": "Lineups endpoint did not return JSON",
            }

        lineups: list[dict] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                lineup_id = (
                    item.get("ID")
                    or item.get("Id")
                    or item.get("id")
                    or item.get("Name")
                    or item.get("name")
                )
                if not lineup_id:
                    continue
                name = (
                    item.get("Name")
                    or item.get("name")
                    or str(lineup_id)
                )
                lineups.append({"id": str(lineup_id), "name": str(name)})
        elif isinstance(data, dict):
            # CDVR returns {source_id: lineup_id} — values are the lineup IDs
            # we PUT to /dvr/lineups/<lineup_id> to refresh the guide.
            for _source_id, lineup_id in data.items():
                if not lineup_id:
                    continue
                lineups.append({"id": str(lineup_id), "name": str(lineup_id)})
        else:
            logger.warning(
                "[%s] Unexpected /dvr/lineups response type: %s",
                self.SERVER_LABEL,
                type(data).__name__,
            )

        return {"success": True, "lineups": lineups}

    def trigger_epg_refresh(self, timeout: int = 60) -> dict:
        """Trigger an XMLTV lineup refresh on the Channels DVR server.

        Without this call CDVR refreshes the M3U channel list but leaves
        the guide data stale — which is the whole reason this integration
        exists. Endpoint: ``PUT /dvr/lineups/<lineup_id>``. Returns
        immediately with the refresh running in the background.

        Returns:
            dict with success, message, duration
        """
        if not self.lineup_id:
            return {
                "success": False,
                "message": "No XMLTV lineup configured",
                "duration": 0,
            }

        start = time.monotonic()
        url = f"{self.base_url}/dvr/lineups/{quote(self.lineup_id, safe='')}"
        try:
            resp = httpx.put(url, timeout=timeout)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            duration = time.monotonic() - start
            if e.response.status_code == 404:
                msg = f"Lineup '{self.lineup_id}' not found"
            else:
                msg = f"EPG refresh failed: HTTP {e.response.status_code}"
            return {"success": False, "message": msg, "duration": duration}
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"EPG refresh failed: {e}",
                "duration": time.monotonic() - start,
            }

        duration = time.monotonic() - start
        logger.info(
            "[%s] Triggered EPG refresh for lineup '%s' in %.2fs",
            self.SERVER_LABEL,
            self.lineup_id,
            duration,
        )
        return {
            "success": True,
            "message": f"EPG refresh triggered for lineup '{self.lineup_id}'",
            "duration": duration,
        }
