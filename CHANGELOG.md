# Changelog

## 0.3.3

- Fixed `DuplicateColumn` (`column "provider" ... already exists`) when running migrations on
  installations that still have the columns from migrations `0003`-`0005` but no longer have
  them recorded in `django_migrations`. These migrations now only add columns that are missing.

## 0.3.2

- Raised `max_version` to `4.7.99`; verified against NetBox 4.7.2 (the plugin was skipped on 4.7.2 before).
- Restored migrations `0003`–`0006`, which had been deleted while the model still uses their fields
  (`provider`, `auth_method`, `token_name`, timeouts, retries, `sync_lxc_containers`). Fresh
  installations were missing these columns. Existing installations already have them recorded as
  applied, so nothing changes there.

## 0.3.1

- Fixed Django migration dependencies for NetBox 4.6.5 through 4.6.8.
- Replaced dynamic `__latest__` dependencies in published migrations with fixed NetBox 4.6 squashed migration names.
- Documented the migration-history issue and the safe upgrade path for affected installations.

### Safe Upgrade Path

If `python manage.py migrate` fails with `InconsistentMigrationHistory` because `netbox_vmware_importer.0001_initial` is applied before a newer NetBox core migration, upgrade the plugin package to version `0.3.1` first and then run migrations normally:

```bash
cd /opt/netbox
source venv/bin/activate

pip install --upgrade --force-reinstall --no-cache-dir git+https://git.mrblake.cc/MrBlake/NetBox-VM-Import.git

cd /opt/netbox/netbox
python manage.py migrate --plan
python manage.py migrate
python manage.py check

sudo systemctl restart netbox netbox-rq
```

No manual edits to the `django_migrations` table and no `--fake` migration should be necessary. Take a database backup before any NetBox or plugin upgrade.

## 0.3.0

- Removed Proxmox sync support.
- Kept legacy Proxmox endpoints visible so administrators can delete old records safely.
- Restricted the plugin UI and sync jobs to VMware vSphere/vCenter endpoints.
