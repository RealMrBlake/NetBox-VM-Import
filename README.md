# NetBox VMware Importer

NetBox plugin zum Synchronisieren von VMware vSphere/vCenter VMs nach NetBox.

## Funktionen

- vCenter/ESXi-Ziele direkt in der NetBox-Weboberflaeche pflegen
- Pro Ziel Tenant, Site und NetBox-Cluster hinterlegen
- Manuelle Synchronisation per Button
- Optionale automatische Synchronisation ueber ein Minutenintervall
- Import von VM-Name, Status, vCPU, RAM, Disk, Plattform, Interfaces, MAC-Adressen und IPs
- MAC-Adressen werden als NetBox MAC Address Objekte am VM-Interface angelegt und als primaere MAC gesetzt
- Virtuelle VMware-Festplatten werden als NetBox Virtual Disks mit Groesse und Backing-Info dokumentiert
- Primaere IPv4/IPv6 wird anhand der ersten gefundenen Gast-IP gesetzt
- Multi-Tenant-sicherer VM-Abgleich ueber `name + cluster`

Das Plugin loescht bewusst keine verwaisten VMs, Interfaces oder IP-Adressen. Damit bleibt der erste Rollout konservativ und vermeidet Datenverlust, wenn VMware-Gastdaten unvollstaendig sind.

## Installation

Im Python-Environment der NetBox-Installation:

```bash
pip install git+https://git.mrblake.cc/MrBlake/NetBox-VM-Import.git
```

NetBox selbst ist keine `pip`-Dependency des Plugins. Das Plugin wird im vorhandenen NetBox-Virtualenv installiert und bringt nur externe Bibliotheken wie `pyvmomi` und `cryptography` mit.

In `configuration.py` aktivieren:

```python
PLUGINS = [
    "netbox_vmware_importer",
]
```

Danach Migrationen anwenden und NetBox/RQ neu starten:

```bash
python manage.py migrate netbox_vmware_importer
sudo systemctl restart netbox netbox-rq
```

## Nutzung

1. In NetBox unter `VMware Import > vCenter Endpoints` ein Ziel anlegen.
2. vCenter Host, Port, Benutzername und Passwort eintragen.
3. Tenant, Site und Cluster fuer den Kunden auswaehlen.
4. Optional Regex-Filter und Sync-Intervall setzen.
5. Auf der Detailseite `Sync jetzt starten` ausfuehren.

Wenn `Sync interval minutes` gesetzt ist, prueft ein Systemjob alle fuenf Minuten, welche Endpoints faellig sind, und stellt die eigentlichen Sync-Jobs in die Queue.

Ab Version `0.1.8` wird beim Speichern eines Endpoints zusaetzlich ein wiederkehrender NetBox-Job fuer genau diesen Endpoint geplant. Nach einem Update vorhandene Endpoints einmal speichern oder `netbox-rq` neu starten und bis zum naechsten Systemjob-Lauf warten.

## Sicherheit

Das vCenter-Passwort wird verschluesselt in der Plugin-Tabelle gespeichert. Der Schluessel wird aus `SECRET_KEY` abgeleitet. Wenn `SECRET_KEY` rotiert wird, muessen die vCenter-Passwoerter in den Endpoints erneut gesetzt werden.

Fuer sehr strenge Umgebungen ist ein externer Secret-Store wie Vault als naechster sinnvoller Ausbaupunkt vorgesehen.

## VMware-Datenqualitaet

IP-Adressen kommen aus den VMware Guest Tools. Ohne laufende bzw. aktuelle VMware Tools koennen Interfaces und IPs fehlen oder veraltet sein.
