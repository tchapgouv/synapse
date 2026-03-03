#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# Copyright (C) 2024 New Vector, Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl-3.0.html>.
#
#

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictStr, StringConstraints
from pydantic.config import ExtraValues
from typing_extensions import Self

from synapse.api.errors import SynapseError
from synapse.events import USE_FROZEN_DICTS
from synapse.types import EventID
from synapse.util.frozenutils import unfreeze


class ParseModel(BaseModel):
    """A custom version of Pydantic's BaseModel which

     - ignores unknown fields,
     - does not allow fields to be overwritten after construction and
     - enables strict mode,

    but otherwise uses Pydantic's default behaviour.

    Strict mode can adversely affect some types of fields, and should be disabled
    for a field if:

    - the field's type is a `Path` or `FilePath`. Strict mode will refuse to
      coerce from `str` (likely what the yaml parser will produce) to `FilePath`,
      raising a `ValidationError`.

    For now, ignore unknown fields. In the future, we could change this so that unknown
    config values cause a ValidationError, provided the error messages are meaningful to
    server operators.

    Subclassing in this way is recommended by
    https://pydantic-docs.helpmanual.io/usage/model_config/#change-behaviour-globally
    """

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        print(f"model_validate: USE_FROZEN_DICTS={USE_FROZEN_DICTS}")
        if USE_FROZEN_DICTS:
            obj = unfreeze(obj)
        return super().model_validate(
            obj,
            strict=strict,
            extra=extra,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )


def validate_event_id_v1_and_2(value: str) -> str:
    try:
        EventID.from_string(value)
    except SynapseError as e:
        raise ValueError from e
    return value


EventIdV1And2 = Annotated[StrictStr, AfterValidator(validate_event_id_v1_and_2)]
EventIdV3Plus = Annotated[
    StrictStr, StringConstraints(pattern=r"^\$([a-zA-Z0-9-_]{43}|[a-zA-Z0-9+/]{43})$")
]
AnyEventId = EventIdV1And2 | EventIdV3Plus
