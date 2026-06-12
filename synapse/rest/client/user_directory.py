#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# Copyright 2017 Vector Creations Ltd
# Copyright (C) 2023 New Vector, Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl-3.0.html>.
#
# Originally licensed under the Apache License, Version 2.0:
# <http://www.apache.org/licenses/LICENSE-2.0>.
#
# [This file includes modifications made by New Vector Limited]
#
#

import logging
from typing import TYPE_CHECKING

from synapse.api.errors import SynapseError
from synapse.api.ratelimiting import Ratelimiter
from synapse.http.server import HttpServer
from synapse.http.servlet import RestServlet, parse_json_object_from_request
from synapse.http.site import SynapseRequest
from synapse.types import JsonMapping

from ._base import client_patterns

if TYPE_CHECKING:
    from synapse.server import HomeServer

logger = logging.getLogger(__name__)


class UserDirectorySearchRestServlet(RestServlet):
    PATTERNS = client_patterns("/user_directory/search$")
    CATEGORY = "User directory search requests"

    def __init__(self, hs: "HomeServer"):
        super().__init__()
        self.hs = hs
        self.auth = hs.get_auth()
        self.user_directory_handler = hs.get_user_directory_handler()

        self._per_user_limiter = Ratelimiter(
            store=hs.get_datastores().main,
            clock=hs.get_clock(),
            cfg=hs.config.ratelimiting.rc_user_directory,
        )
        self.msc4258_enabled = self.hs.config.experimental.msc4258_enabled
        self.msc4258_federation_search_max_result = (
            self.hs.config.experimental.msc4258_federation_search_max_result
        )

    async def on_POST(self, request: SynapseRequest) -> tuple[int, JsonMapping]:
        """Searches for users in directory, including federated results

        Request:
            {
                "search_term": "search query",
                "limit": 10,
            }

        Returns:
            dict of the form::

                {
                    "limited": <bool>,  # whether there were more results or not
                    "results": [  # Ordered by best match first
                        {
                            "user_id": <user_id>,
                            "display_name": <display_name>,
                            "avatar_url": <avatar_url>
                        }
                    ]
                }
        """
        requester = await self.auth.get_user_by_req(request, allow_guest=False)
        user_id = requester.user.to_string()

        if not self.hs.config.userdirectory.user_directory_search_enabled:
            return 200, {"limited": False, "results": []}

        await self._per_user_limiter.ratelimit(requester)

        body = parse_json_object_from_request(request)

        limit = int(body.get("limit", 10))
        limit = max(min(limit, self.msc4258_federation_search_max_result), 0)

        try:
            search_term = body["search_term"]
        except Exception:
            raise SynapseError(400, "`search_term` is required field")

        # Not triggering any search for less than 3 chars if MSC4258 is enabled
        if self.msc4258_enabled and search_term and len(search_term) < 4:
            return 200, {"limited": False, "results": []}

        # Get local results first
        local_results = await self.user_directory_handler.search_users(
            user_id, search_term, limit
        )

        # If MSC4258 is not enabled this should work as before
        if not self.msc4258_enabled:
            return 200, local_results

        # Return local result if we have reach limit (no need to call federation search)
        if len(local_results) > limit:
            return 200, local_results

        # Try to get federated results
        federated_results = (
            await self.user_directory_handler.get_federated_search_results(
                user_id, search_term, limit
            )
        )

        return 200, merge_search_results(local_results, federated_results, limit)


def register_servlets(hs: "HomeServer", http_server: HttpServer) -> None:
    UserDirectorySearchRestServlet(hs).register(http_server)


def merge_search_results(
    local_results: JsonMapping, federated_results: JsonMapping, limit: int
) -> JsonMapping:
    """
    Merge local results and federated results.
    We prioritize the local result then federated results.
    """
    concatenation = local_results["results"] + federated_results["results"]

    # Remove duplicates as local homeservers may know some of the federated users
    seen = set()
    results = []
    for user in concatenation:
        if user["user_id"] not in seen:
            seen.add(user["user_id"])
            results.append(user)

    limited = False
    # Limit the total number of results
    if len(results) > limit:
        results = results[:limit]
        limited = True

    # Sort results by display name (case insensitive)
    results.sort(
        key=lambda user: (
            user.get("display_name", "").lower() if user.get("display_name") else "",
            user.get("user_id", ""),
        )
    )

    return {
        "limited": limited,
        "results": results,
    }
