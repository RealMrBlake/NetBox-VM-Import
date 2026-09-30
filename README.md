# NetBox VMware Importer

Synchronise virtual machines from VMware vSphere / vCenter into NetBox.

| | |
|---|---|
| **Plugin name** | `netbox_vmware_importer` |
| **Package** | `netbox-vmware-importer` |
| **NetBox** | `4.6.5` – `4.7.1` |
| **Python** | `>=3.12` |
| **Repository** | <https://git.mrblake.cc/MrBlake/NetBox-VM-Import> |

## Features

- Manage vCenter/ESXi endpoints directly in the NetBox web UI
- Tenant, site and NetBox cluster per endpoint
- Manual synchronisation via button
- Optional automatic synchronisation on a minute interval
- Imports VM name, status, vCPU, RAM, disk, platform, interfaces, MAC addresses and IPs
- MAC addresses are created as NetBox MAC address objects on the VM interface and set as primary MAC
- Virtual disks are documented as NetBox virtual disks with size and backing info
- Primary IPv4/IPv6 is set from the first guest IP found
- Multi-tenant-safe VM matching via `name + cluster`

The plugin intentionally does **not** delete orphaned VMs, interfaces or IP
addresses. This keeps rollouts conservative and avoids data loss when VMware
guest data is incomplete.

## Compatibility

- NetBox `4.6.5` – `4.7.1`
- Python `>=3.12`
- Dependencies installed automatically: `pyvmomi`, `cryptography`

## Installation

All paths assume a standard installation under `/opt/netbox`.

### 1. Install the package

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/NetBox-VM-Import.git@main"
```

For reproducible production installs, replace `main` with a release tag or a
full commit ID.

### 2. Add the plugin to `local_requirements.txt`

This makes `upgrade.sh` reinstall the plugin automatically on every NetBox upgrade:

```bash
grep -qxF "git+https://git.mrblake.cc/MrBlake/NetBox-VM-Import.git@main" /opt/netbox/local_requirements.txt \
  || echo "git+https://git.mrblake.cc/MrBlake/NetBox-VM-Import.git@main" | sudo tee -a /opt/netbox/local_requirements.txt
```

If the repository is private, the NetBox server needs a read-only deploy token
or an SSH key. Do not store credentials in `local_requirements.txt`.

### 3. Enable the plugin

In `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = [
    "netbox_vmware_importer",
]
```

If other plugins are already configured, add `netbox_vmware_importer` to the
existing list.

### 4. Apply migrations, collect static files, restart

```bash
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate netbox_vmware_importer
/opt/netbox/venv/bin/python manage.py collectstatic --no-input
sudo systemctl restart netbox netbox-rq
```

## Update

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/NetBox-VM-Import.git@main"

cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate netbox_vmware_importer
/opt/netbox/venv/bin/python manage.py collectstatic --no-input
sudo systemctl restart netbox netbox-rq
```

`--force-reinstall` makes pip pick up branch changes even if the package
version has not been bumped.

When NetBox itself is upgraded, `upgrade.sh` reinstalls the plugin from
`local_requirements.txt` and runs migrations and `collectstatic`:

```bash
sudo /opt/netbox/upgrade.sh
sudo systemctl restart netbox netbox-rq
```

### Upgrade note for 0.3.1

Version `0.3.1` fixes unstable Django migration dependencies from earlier
releases. If `migrate` fails with `InconsistentMigrationHistory` for
`netbox_vmware_importer.0001_initial`, first update the plugin to `0.3.1`, then
run `manage.py migrate --plan` and `manage.py migrate` normally. Manual changes
to `django_migrations` or `--fake` should not be necessary.

## Uninstall

1. Remove `"netbox_vmware_importer"` from `PLUGINS`.
2. Remove the line from `/opt/netbox/local_requirements.txt`.
3. Uninstall the package and restart NetBox:

```bash
/opt/netbox/venv/bin/pip uninstall netbox-vmware-importer
sudo systemctl restart netbox netbox-rq
```

## Usage

1. In NetBox, create an endpoint under **VMware Import > Endpoints**.
2. Enter the vCenter/ESXi host, port, username and password.
3. Select tenant, site and cluster for the customer.
4. Optionally set regex filters and a sync interval.
5. On the detail page, click **Start sync now**.

If **Sync interval minutes** is set, a system job checks every five minutes
which endpoints are due and enqueues the actual sync jobs.

### Legacy Proxmox endpoints

Proxmox support has been removed. Old Proxmox endpoints from earlier versions
remain visible in the list and detail view so they can be deleted; they can no
longer be edited, created or synchronised.

## Security

The endpoint password is stored encrypted in the plugin table. The key is
derived from `SECRET_KEY`; if `SECRET_KEY` is rotated, the endpoint secrets must
be set again. For very strict environments, an external secret store such as
Vault is the next planned extension.

## Data quality

IP addresses come from VMware Guest Tools. Without running or current Guest
Tools, interfaces and IPs may be missing or outdated.
