from flask.blueprints import BlueprintSetupState
from werkzeug.routing import IntegerConverter, ValidationError

MAX_OWNER_ID = 2_147_483_647


class OwnerIdConverter(IntegerConverter):
    def to_python(self, value: str) -> int:
        try:
            owner_id = super().to_python(value)
        except ValueError:
            # Python rejects extremely long decimal strings before range validation.
            raise ValidationError() from None
        if not 1 <= owner_id <= MAX_OWNER_ID:
            raise ValidationError()
        return owner_id


def register_owner_id_converter(state: BlueprintSetupState) -> None:
    state.app.url_map.converters["owner_id"] = OwnerIdConverter
