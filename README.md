# NetBox VMware & Proxmox Importer

NetBox plugin zum Synchronisieren von VMware vSphere/vCenter und Proxmox VE VMs nach NetBox.

## Funktionen

- vCenter/ESXi-Ziele direkt in der NetBox-Weboberflaeche pflegen
- Proxmox VE-Ziele direkt in der NetBox-Weboberflaeche pflegen
- Pro Ziel Tenant, Site und NetBox-Cluster hinterlegen
- Manuelle Synchronisation per Button
- Optionale automatische Synchronisation ueber ein Minutenintervall
- Import von VM-Name, Status, vCPU, RAM, Disk, Plattform, Interfaces, MAC-Adressen und IPs
- MAC-Adressen werden als NetBox MAC Address Objekte am VM-Interface angelegt und als primaere MAC gesetzt
- Virtuelle Festplatten werden als NetBox Virtual Disks mit Groesse und Backing-Info dokumentiert
- Primaere IPv4/IPv6 wird anhand der ersten gefundenen Gast-IP gesetzt
- Multi-Tenant-sicherer VM-Abgleich ueber `name + cluster`

Das Plugin loescht bewusst keine verwaisten VMs, Interfaces oder IP-Adressen. Damit bleibt der erste Rollout konservativ und vermeidet Datenverlust, wenn Hypervisor-Gastdaten unvollstaendig sind.

## Installation

Im Python-Environment der NetBox-Installation:

```bash
pip install git+https://git.mrblake.cc/MrBlake/NetBox-VM-Import.git
```

NetBox selbst ist keine `pip`-Dependency des Plugins. Das Plugin wird im vorhandenen NetBox-Virtualenv installiert und bringt nur externe Bibliotheken wie `pyvmomi`, `cryptography`, `requests` und `proxmox-sdk` mit.

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

1. In NetBox unter `VM Import > Endpoints` ein Ziel anlegen.
2. Provider auswaehlen.
3. VMware: vCenter Host, Port, Benutzername und Passwort eintragen.
4. Proxmox: Proxmox Host, Port `8006`, Benutzername inklusive Realm und Passwort oder API-Token eintragen, z. B. `root@pam`.
5. Tenant, Site und Cluster fuer den Kunden auswaehlen.
6. Optional Regex-Filter und Sync-Intervall setzen.
7. Auf der Detailseite `Sync jetzt starten` ausfuehren.

Bei selbstsignierten Proxmox-Zertifikaten `Validate SSL` deaktiviert lassen. Wenn Proxmox langsam antwortet, kann `API timeout` am Endpoint erhoeht werden.

Der Proxmox-Client nutzt fuer API-Token bevorzugt `proxmox-sdk` wie `netbox-proxbox`/`proxbox-api`. Passwort-Logins laufen ueber den eigenen `requests`-Client, weil `proxmox-sdk==0.0.12` die Ticket-URL fuer Passwort-Authentifizierung ohne `/api2/json` aufbaut. Proxy-Umgebungsvariablen des NetBox-Dienstes werden im `requests`-Client ignoriert, damit interne Proxmox-Adressen nicht versehentlich ueber einen HTTPS-Proxy laufen.

Im `requests`-Fallback ist der unauthentifizierte Proxmox-`version`-Probe nur diagnostisch. Wenn er haengt, versucht das Plugin den eigentlichen Login trotzdem. Im bevorzugten SDK-Pfad wird `version` als erste SDK-Anfrage genutzt und authentifiziert dabei automatisch.

Proxmox-API-Verbindungen nutzen TLS 1.2-Kompatibilitaetsmodus, weil einige Firewalls oder TLS-Inspektionspfade moderne TLS-1.3-ClientHellos blockieren.

Bei Proxmox koennen `Connect timeout`, `API timeout`, `GET retries` und `Retry backoff` pro Endpoint gesetzt werden. Das entspricht dem Ansatz von Proxbox, Verbindungs- und Retry-Parameter pro Proxmox-Ziel zu speichern.

Wenn Passwort-Login auf `access/ticket` haengt, zuerst den Realm im Benutzernamen pruefen (`root@pam`, `user@pve`, `user@ldaprealm`). Fuer produktive Imports ist ein Proxmox API-Token meistens stabiler als Passwort-Login.

Wenn `Sync interval minutes` gesetzt ist, prueft ein Systemjob alle fuenf Minuten, welche Endpoints faellig sind, und stellt die eigentlichen Sync-Jobs in die Queue.

Ab Version `0.1.8` wird beim Speichern eines Endpoints zusaetzlich ein wiederkehrender NetBox-Job fuer genau diesen Endpoint geplant. Nach einem Update vorhandene Endpoints einmal speichern oder `netbox-rq` neu starten und bis zum naechsten Systemjob-Lauf warten.

## Sicherheit

Das Endpoint-Passwort bzw. Token-Secret wird verschluesselt in der Plugin-Tabelle gespeichert. Der Schluessel wird aus `SECRET_KEY` abgeleitet. Wenn `SECRET_KEY` rotiert wird, muessen die Secrets in den Endpoints erneut gesetzt werden.

Fuer sehr strenge Umgebungen ist ein externer Secret-Store wie Vault als naechster sinnvoller Ausbaupunkt vorgesehen.

## Datenqualitaet

IP-Adressen kommen bei VMware aus den VMware Guest Tools und bei Proxmox-QEMU aus dem QEMU Guest Agent. Ohne laufende bzw. aktuelle Guest Tools koennen Interfaces und IPs fehlen oder veraltet sein.
