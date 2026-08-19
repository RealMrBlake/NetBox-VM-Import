import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0001_squashed"),
        ("netbox_vmware_importer", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="created",
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True, verbose_name="created"),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="last_updated",
            field=models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="last updated"),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
        ),
        migrations.AddField(
            model_name="vcenterendpoint",
            name="tags",
            field=taggit.managers.TaggableManager(
                help_text="A comma-separated list of tags.",
                through="extras.TaggedItem",
                to="extras.Tag",
                verbose_name="Tags",
            ),
        ),
    ]
