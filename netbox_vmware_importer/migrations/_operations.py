from django.db import migrations


class AddFieldIfMissing(migrations.AddField):
    """
    AddField that leaves an already existing column alone.

    Migrations 0003-0005 were temporarily removed from the repository. Installations that
    applied them before that still have the columns, but may no longer have the matching
    django_migrations rows, so a plain AddField would fail with DuplicateColumn.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        column = model._meta.get_field(self.name).column
        connection = schema_editor.connection
        with connection.cursor() as cursor:
            existing = {
                col.name for col in connection.introspection.get_table_description(cursor, model._meta.db_table)
            }
        if column in existing:
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
