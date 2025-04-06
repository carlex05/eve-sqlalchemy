from cerberus import Validator, TypeDefinition
from eve.utils import config
from eve.versioning import (
    get_data_version_relation_document, missing_version_field,
)
from flask import current_app as app

class ValidatorSQL(Validator):
    types_mapping = Validator.types_mapping.copy()
    types_mapping.update({
        'objectid': TypeDefinition('objectid', (str,), ()),  # O el tipo más apropiado en tu caso
        'json': TypeDefinition('json', (dict,), ())          # json validado como dict
    })

    def __init__(self, schema, resource=None, **kwargs):
        self.resource = resource
        self._id = None
        self._original_document = None
        kwargs['transparent_schema_rules'] = True
        super().__init__(schema, **kwargs)
        if resource:
            self.allow_unknown = config.DOMAIN[resource]['allow_unknown']

    def validate_update(self, document, _id, original_document=None):
        self._id = _id
        self._original_document = original_document
        return super().validate(document)

    def validate_replace(self, document, _id, original_document=None):
        self._id = _id
        self._original_document = original_document
        return super().validate(document)

    def _validate_unique(self, unique, field, value):
        if unique:
            id_field = config.DOMAIN[self.resource]['id_field']
            if field == id_field and value == self._id:
                return
            elif field != id_field and self._id is not None:
                query = {field: value, id_field: f"!= '{self._id}'"}
            else:
                query = {field: value}

            if app.data.find_one(self.resource, None, **query):
                self._error(field, f"value '{value}' is not unique")

    def _validate_data_relation(self, data_relation, field, value):
        if 'version' in data_relation and data_relation['version']:
            value_field = data_relation['field']
            version_field = app.config['VERSION']

            if isinstance(value, dict) and value_field in value and version_field in value:
                resource_def = config.DOMAIN[data_relation['resource']]
                if resource_def['versioning'] is False:
                    self._error(field, 
                        f"can't save a version with data_relation if '{data_relation['resource']}' isn't versioned")
                else:
                    search = (
                        missing_version_field(data_relation, value)
                        if value[version_field] == 0 else
                        get_data_version_relation_document(data_relation, value)
                    )
                    if not search:
                        self._error(field, 
                            f"value '{value[value_field]}' must exist in resource '{data_relation['resource']}', field '{data_relation['field']}' at version '{value[version_field]}'.")
            else:
                self._error(field, 
                    f"versioned data_relation must be a dict with fields '{value_field}' and '{version_field}'")
        else:
            query = {data_relation['field']: value}
            if not app.data.find_one(data_relation['resource'], None, **query):
                self._error(field, 
                    f"value '{value}' must exist in resource '{data_relation['resource']}', field '{data_relation['field']}'")

    def _validate_readonly(self, read_only, field, value):
        original_value = self._original_document.get(field) if self._original_document else None
        if value != original_value:
            super()._validate_readonly(read_only, field, value)

    def _validate_dependencies(self, document, dependencies, field, break_on_error=False):
        return super()._validate_dependencies(document, dependencies, field, break_on_error)

    def _error(self, *args):
        if len(args) == 1 and isinstance(args[0], list):
            super()._error(args[0])
        else:
            super()._error(*args)

        if config.VALIDATION_ERROR_AS_LIST:
            # Asegurarse que _errors siempre sea una lista
            for field in self._errors:
                err = self._errors[field]
                if not isinstance(err, list):
                    self._errors[field] = [err]
