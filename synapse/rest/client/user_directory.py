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
from typing import TYPE_CHECKING, Tuple

from synapse.api.errors import SynapseError
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
        self.federation_client = hs.get_federation_client()
        self.state = hs.get_state_handler()

    async def on_POST(self, request: SynapseRequest) -> Tuple[int, JsonMapping]:
        """Searches for users in directory, including federated results

        Request:
            {
                "search_term": "search query",
                "limit": 10,
                "include_federation": true  # Optional, defaults to false
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

        body = parse_json_object_from_request(request)

        limit = int(body.get("limit", 10))
        limit = max(min(limit, 50), 0)

        try:
            search_term = body["search_term"]
        except Exception:
            raise SynapseError(400, "`search_term` is required field")

        # Get local results first
        local_results = await self.user_directory_handler.search_users(
            user_id, search_term, limit
        )

        # Check if federation search is requested
        if not body.get("include_federation", False):
            return 200, local_results

        # Get the list of rooms the user is in
        rooms = await self.state.get_current_user_in_room_ids(user_id)
        
        # Get the list of servers in those rooms
        servers_in_rooms = set()
        for room_id in rooms:
            servers_in_room = await self.state.get_current_hosts_in_room(room_id)
            servers_in_rooms.update(servers_in_room)
        
        # Remove our own server
        servers_in_rooms.discard(self.hs.hostname)
        servers = list(servers_in_rooms)

        # If no remote servers to query, just return local results
        if not servers:
            return 200, local_results

        # Query federated servers
        federated_results = await self.federation_client.search_user_directory_across_federation(
            servers, search_term, limit
        )

        # Combine local and federated results
        combined_results = local_results.get("results", []) + federated_results.get("results", [])
        
        # Remove duplicates (by user_id)
        seen_user_ids = set()
        unique_results = []
        for user in combined_results:
            if user["user_id"] not in seen_user_ids:
                seen_user_ids.add(user["user_id"])
                unique_results.append(user)

        # Sort results by display name (case insensitive)
        unique_results.sort(
            key=lambda user: (
                user.get("display_name", "").lower() if user.get("display_name") else "",
                user.get("user_id", ""),
            )
        )

        # Limit the total number of results
        limited = len(unique_results) > limit
        if limited:
            unique_results = unique_results[:limit]

        return 200, {"limited": limited, "results": unique_results}


def register_servlets(hs: "HomeServer", http_server: HttpServer) -> None:
    UserDirectorySearchRestServlet(hs).register(http_server)
