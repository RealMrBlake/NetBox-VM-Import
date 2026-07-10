import ipaddress
import re
import ssl
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Sum
from dcim.models import MACAddress, Platform
from ipam.models import IPAddress
from virtualization.models import VMInterface, VirtualDisk, VirtualMachine

from .choices import EndpointAuthMethodChoices, EndpointProviderChoices

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.exceptions import InsecureRequestWarning
except ImportError:  # pragma: no cover - handled at runtime inside NetBox
    HTTPAdapter = None
    requests = None
    InsecureRequestWarning = None

try:
    from pyVim.connect import Disconnect, SmartConnect
    from pyVmomi import vim
except ImportError:  # pragma: no cover - handled at runtime inside NetBox
    Disconnect = None
    SmartConnect = None
    vim = None


@dataclass
class InterfaceData:
    name: str
    mac_address: str
    ip_addresses: list[str] = field(default_factory=list)


@dataclass
class DiskData:
    name: str
    size_mb: int
    description: str = ""


@dataclass
class VMData:
    name: str
    status: str
    vcpus: int
    memory_mb: int
    disk_mb: int
    guest_os: str = ""
    disks: list[DiskData] = field(default_factory=list)
    interfaces: list[InterfaceData] = field(default_factory=list)


@dataclass
class SyncResult:
    seen: int = 0
    synced: int = 0
    skipped: int = 0
    created: int = 0
    updated: int = 0
    errors: int = 0
    interfaces_created: int = 0
    interfaces_updated: int = 0
    ip_addresses_created: int = 0
    ip_addresses_updated: int = 0
    ip_conflicts: int = 0
    mac_addresses_created: int = 0
    mac_addresses_updated: int = 0
    mac_addresses_deleted: int = 0
    virtual_disks_created: int = 0
    virtual_disks_updated: int = 0
    virtual_disks_deleted: int = 0


class VMwareConnectionError(RuntimeError):
    pass


class ProxmoxConnectionError(RuntimeError):
    pass


class ProxmoxTLSCompatibilityAdapter(HTTPAdapter):
    def __init__(self, validate_ssl=True, *args, **kwargs):
        self.validate_ssl = validate_ssl
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["ssl_context"] = self._build_ssl_context()
        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._build_ssl_context()
        return super().proxy_manager_for(*args, **kwargs)

    def _build_ssl_context(self):
        context = ssl.create_default_context()
        if hasattr(ssl, "TLSVersion"):
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.maximum_version = ssl.TLSVersion.TLSv1_2
        if not self.validate_ssl:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context


class VMwareClient:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.service_instance = None

    def __enter__(self):
        if SmartConnect is None:
            raise VMwareConnectionError("pyVmomi is not installed in the NetBox Python environment.")

        ssl_context = None
        if not self.endpoint.validate_ssl:
            ssl_context = ssl._create_unverified_context()

        self.service_instance = SmartConnect(
            host=self.endpoint.host,
            port=self.endpoint.port,
            user=self.endpoint.username,
            pwd=self.endpoint.password,
            sslContext=ssl_context,
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.service_instance is not None and Disconnect is not None:
            Disconnect(self.service_instance)

    def iter_virtual_machines(self):
        content = self.service_instance.RetrieveContent()
        container_view = content.viewManager.CreateContainerView(
            content.rootFolder,
            [vim.VirtualMachine],
            True,
        )

        try:
            for vm_obj in container_view.view:
                yield self._build_vm_data(vm_obj)
        finally:
            container_view.Destroy()

    def _build_vm_data(self, vm_obj):
        config = getattr(vm_obj, "config", None)
        hardware = getattr(config, "hardware", None)

        memory_mb = int(getattr(hardware, "memoryMB", 0) or 0)
        vcpus = int(getattr(hardware, "numCPU", 0) or 0)
        disks = self._get_disks(hardware)
        disk_mb = sum(disk.size_mb for disk in disks)
        guest_os = getattr(config, "guestFullName", "") or ""
        power_state = str(getattr(getattr(vm_obj, "runtime", None), "powerState", ""))
        status = "active" if "poweredOn" in power_state else "offline"

        return VMData(
            name=vm_obj.name,
            status=status,
            vcpus=vcpus,
            memory_mb=memory_mb,
            disk_mb=disk_mb,
            guest_os=guest_os,
            disks=disks,
            interfaces=self._get_interfaces(vm_obj),
        )

    @staticmethod
    def _get_disks(hardware):
        disks = []
        used_names = set()
        disk_index = 0

        for device in getattr(hardware, "device", []) or []:
            if isinstance(device, vim.vm.device.VirtualDisk):
                disk_index += 1
                name = VMwareClient._unique_disk_name(device, disk_index, used_names)
                disks.append(
                    DiskData(
                        name=name,
                        size_mb=round((device.capacityInKB or 0) / 1024),
                        description=VMwareClient._disk_description(device),
                    )
                )

        return disks

    @staticmethod
    def _unique_disk_name(device, disk_index, used_names):
        device_info = getattr(device, "deviceInfo", None)
        base_name = getattr(device_info, "label", None) or f"Hard disk {disk_index}"
        base_name = VMwareClient._truncate_component_name(str(base_name).strip() or f"Hard disk {disk_index}")

        name = base_name
        suffix = 2
        while name in used_names:
            suffix_text = f" ({suffix})"
            name = f"{base_name[:64 - len(suffix_text)]}{suffix_text}"
            suffix += 1

        used_names.add(name)
        return name

    @staticmethod
    def _truncate_component_name(value):
        return value[:64]

    @staticmethod
    def _disk_description(device):
        backing = getattr(device, "backing", None)
        filename = getattr(backing, "fileName", None)
        thin_provisioned = getattr(backing, "thinProvisioned", None)

        parts = []
        if filename:
            parts.append(str(filename))
        if thin_provisioned is not None:
            parts.append("thin" if thin_provisioned else "thick")

        detail = ", ".join(parts) if parts else f"key={getattr(device, 'key', 'unknown')}"
        return f"VMware: {detail}"[:200]

    @staticmethod
    def _get_interfaces(vm_obj):
        interfaces = []
        guest = getattr(vm_obj, "guest", None)

        for network in getattr(guest, "net", []) or []:
            mac_address = getattr(network, "macAddress", None)
            if not mac_address:
                continue

            name = getattr(network, "device", None) or f"NIC-{mac_address[-5:].replace(':', '')}"
            interfaces.append(
                InterfaceData(
                    name=name,
                    mac_address=mac_address,
                    ip_addresses=list(getattr(network, "ipAddress", []) or []),
                )
            )

        return interfaces


class ProxmoxClient:
    DISK_KEY_PATTERN = re.compile(r"^(ide|sata|scsi|virtio)\d+$")
    LXC_DISK_KEY_PATTERN = re.compile(r"^(rootfs|mp\d+)$")
    NET_KEY_PATTERN = re.compile(r"^net\d+$")

    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.session = None
        self.base_url = f"https://{endpoint.host}:{endpoint.port}/api2/json"
        self.timeout = (10, endpoint.request_timeout_seconds or 120)
        self.api_probe_succeeded = False

    def __enter__(self):
        if requests is None:
            raise ProxmoxConnectionError("requests is not installed in the NetBox Python environment.")
        if "@" not in self.endpoint.username:
            raise ProxmoxConnectionError("Proxmox username must include a realm, e.g. root@pam or user@pve.")

        self.session = requests.Session()
        self.session.trust_env = False
        self.session.verify = self.endpoint.validate_ssl
        if HTTPAdapter is not None:
            self.session.mount("https://", ProxmoxTLSCompatibilityAdapter(validate_ssl=self.endpoint.validate_ssl))
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Connection": "close",
                "User-Agent": "netbox-vm-import/0.2",
            }
        )
        if not self.endpoint.validate_ssl and InsecureRequestWarning is not None:
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

        self._probe_api_availability()

        if self.endpoint.auth_method == EndpointAuthMethodChoices.METHOD_API_TOKEN:
            token_id = self.endpoint.token_name if "!" in self.endpoint.token_name else f"{self.endpoint.username}!{self.endpoint.token_name}"
            self.session.headers.update({"Authorization": f"PVEAPIToken={token_id}={self.endpoint.password}"})
        else:
            self._authenticate_with_password()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.session is not None:
            self.session.close()

    def _probe_api_availability(self):
        try:
            self._request("GET", "version", timeout=(5, 10))
            self.api_probe_succeeded = True
            self.api_probe_error = ""
        except ProxmoxConnectionError as exc:
            self.api_probe_succeeded = False
            self.api_probe_error = str(exc)

    def _authenticate_with_password(self):
        response = self._request(
            "POST",
            "access/ticket",
            data={
                "username": self.endpoint.username,
                "password": self.endpoint.password,
            },
        )
        data = response.json().get("data") or {}
        ticket = data.get("ticket")
        csrf_token = data.get("CSRFPreventionToken")

        if not ticket:
            raise ProxmoxConnectionError("Proxmox authentication did not return a ticket.")

        self.session.cookies.set("PVEAuthCookie", ticket)
        if csrf_token:
            self.session.headers.update({"CSRFPreventionToken": csrf_token})

    def _url(self, path):
        return f"{self.base_url}/{path.strip('/')}"

    def _request(self, method, path, timeout=None, **kwargs):
        url = self._url(path)
        request_timeout = timeout or self.timeout
        try:
            response = self.session.request(method, url, timeout=request_timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.ConnectTimeout as exc:
            raise ProxmoxConnectionError(
                f"Proxmox API {method} {path} connect timed out after {request_timeout[0]} seconds."
            ) from exc
        except requests.ReadTimeout as exc:
            detail = f"Proxmox API {method} {path} read timed out after {request_timeout[1]} seconds."
            if path == "access/ticket" and self.api_probe_succeeded:
                detail += " API version endpoint responded, so the delay is likely in Proxmox authentication. Check username realm (e.g. root@pam), PAM/LDAP auth, two-factor auth, or use an API token."
            elif getattr(self, "api_probe_error", "") and path != "version":
                detail += f" Earlier unauthenticated version probe also failed: {self.api_probe_error}"
            raise ProxmoxConnectionError(detail) from exc
        except requests.exceptions.SSLError as exc:
            raise ProxmoxConnectionError(
                f"Proxmox API {method} {path} TLS validation failed. Disable Validate SSL for self-signed certificates or install the CA certificate. Details: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise ProxmoxConnectionError(f"Proxmox API {method} {path} failed: {exc}") from exc

    def _get(self, path, params=None):
        response = self._request("GET", path, params=params)
        return response.json().get("data")

    def iter_virtual_machines(self):
        resources = self._get("cluster/resources", params={"type": "vm"}) or []

        for resource in resources:
            vm_type = resource.get("type")
            if vm_type == "lxc" and not self.endpoint.sync_lxc_containers:
                continue
            if vm_type not in ("qemu", "lxc"):
                continue

            yield self._build_vm_data(resource)

    def _build_vm_data(self, resource):
        vmid = resource["vmid"]
        node = resource["node"]
        vm_type = resource["type"]
        config = self._get(f"nodes/{node}/{vm_type}/{vmid}/config") or {}

        name = resource.get("name") or config.get("name") or config.get("hostname") or f"{vm_type}-{vmid}"
        status = "active" if resource.get("status") == "running" else "offline"
        memory_mb = self._get_memory_mb(resource, config)
        vcpus = self._get_vcpus(resource, config)

        if vm_type == "qemu":
            disks = self._get_qemu_disks(config)
            interfaces = self._get_qemu_interfaces(config)
            self._merge_qemu_agent_interfaces(node, vmid, interfaces)
            guest_os = self._get_qemu_guest_os(node, vmid)
        else:
            disks = self._get_lxc_disks(config)
            interfaces = self._get_lxc_interfaces(config)
            guest_os = "Linux Container"

        disk_mb = sum(disk.size_mb for disk in disks) or self._bytes_to_mb(resource.get("maxdisk"))

        return VMData(
            name=str(name),
            status=status,
            vcpus=vcpus,
            memory_mb=memory_mb,
            disk_mb=disk_mb,
            guest_os=guest_os,
            disks=disks,
            interfaces=interfaces,
        )

    @staticmethod
    def _get_memory_mb(resource, config):
        memory = config.get("memory")
        if memory not in (None, ""):
            try:
                return int(memory)
            except (TypeError, ValueError):
                pass

        return ProxmoxClient._bytes_to_mb(resource.get("maxmem"))

    @staticmethod
    def _get_vcpus(resource, config):
        try:
            sockets = int(config.get("sockets") or 1)
            cores = int(config.get("cores") or resource.get("maxcpu") or 0)
            return max(sockets * cores, 0)
        except (TypeError, ValueError):
            return int(resource.get("maxcpu") or 0)

    @staticmethod
    def _bytes_to_mb(value):
        try:
            return round(int(value or 0) / 1024 / 1024)
        except (TypeError, ValueError):
            return 0

    def _get_qemu_disks(self, config):
        disks = []

        for key, value in sorted(config.items()):
            if not self.DISK_KEY_PATTERN.match(key):
                continue
            parsed = self._parse_proxmox_value(value)
            if parsed.get("media") == "cdrom":
                continue

            size_mb = self._parse_size_mb(parsed.get("size"))
            if size_mb <= 0:
                continue

            disks.append(
                DiskData(
                    name=key,
                    size_mb=size_mb,
                    description=f"Proxmox: {str(value)[:191]}",
                )
            )

        return disks

    def _get_lxc_disks(self, config):
        disks = []

        for key, value in sorted(config.items()):
            if not self.LXC_DISK_KEY_PATTERN.match(key):
                continue

            parsed = self._parse_proxmox_value(value)
            size_mb = self._parse_size_mb(parsed.get("size"))
            if size_mb <= 0:
                continue

            disks.append(
                DiskData(
                    name=key,
                    size_mb=size_mb,
                    description=f"Proxmox: {str(value)[:191]}",
                )
            )

        return disks

    def _get_qemu_interfaces(self, config):
        interfaces = []

        for key, value in sorted(config.items()):
            if not self.NET_KEY_PATTERN.match(key):
                continue

            parsed = self._parse_proxmox_value(value)
            mac_address = self._extract_proxmox_mac(parsed)
            if not mac_address:
                continue

            bridge = parsed.get("bridge")
            name = f"{key} ({bridge})" if bridge else key
            interfaces.append(InterfaceData(name=name[:64], mac_address=mac_address))

        return interfaces

    def _get_lxc_interfaces(self, config):
        interfaces = []

        for key, value in sorted(config.items()):
            if not self.NET_KEY_PATTERN.match(key):
                continue

            parsed = self._parse_proxmox_value(value)
            mac_address = parsed.get("hwaddr")
            if not mac_address:
                continue

            name = parsed.get("name") or key
            ip_addresses = []
            for ip_key in ("ip", "ip6"):
                ip_value = parsed.get(ip_key)
                if ip_value and ip_value not in ("dhcp", "manual", "auto"):
                    ip_addresses.append(ip_value)

            interfaces.append(
                InterfaceData(
                    name=str(name)[:64],
                    mac_address=mac_address,
                    ip_addresses=ip_addresses,
                )
            )

        return interfaces

    def _merge_qemu_agent_interfaces(self, node, vmid, interfaces):
        try:
            response = self._get(f"nodes/{node}/qemu/{vmid}/agent/network-get-interfaces") or {}
        except (requests.RequestException, ProxmoxConnectionError):
            return

        agent_interfaces = response.get("result") if isinstance(response, dict) else response
        if not isinstance(agent_interfaces, list):
            return

        interfaces_by_mac = {self._normalize_mac(interface.mac_address): interface for interface in interfaces}

        for agent_interface in agent_interfaces:
            mac_address = agent_interface.get("hardware-address")
            normalized_mac = self._normalize_mac(mac_address)
            if not normalized_mac:
                continue

            ip_addresses = []
            for ip_data in agent_interface.get("ip-addresses") or []:
                ip_address = ip_data.get("ip-address")
                prefix = ip_data.get("prefix")
                if not ip_address:
                    continue
                if prefix is not None:
                    ip_addresses.append(f"{ip_address}/{prefix}")
                else:
                    ip_addresses.append(ip_address)

            if normalized_mac in interfaces_by_mac:
                interfaces_by_mac[normalized_mac].ip_addresses = ip_addresses
            else:
                interfaces.append(
                    InterfaceData(
                        name=str(agent_interface.get("name") or f"NIC-{normalized_mac[-5:]}")[:64],
                        mac_address=normalized_mac,
                        ip_addresses=ip_addresses,
                    )
                )

    def _get_qemu_guest_os(self, node, vmid):
        try:
            response = self._get(f"nodes/{node}/qemu/{vmid}/agent/get-osinfo") or {}
        except (requests.RequestException, ProxmoxConnectionError):
            return ""

        result = response.get("result") if isinstance(response, dict) else None
        if not isinstance(result, dict):
            return ""

        return result.get("pretty-name") or result.get("name") or ""

    @staticmethod
    def _parse_proxmox_value(value):
        parsed = {"_raw": str(value)}
        parts = str(value).split(",")
        if parts:
            parsed["_first"] = parts[0]

        for part in parts:
            if "=" in part:
                key, part_value = part.split("=", 1)
                parsed[key.strip()] = part_value.strip()

        return parsed

    @staticmethod
    def _extract_proxmox_mac(parsed):
        for key in ("virtio", "e1000", "e1000e", "rtl8139", "vmxnet3", "hwaddr"):
            if parsed.get(key):
                return parsed[key]
        return None

    @staticmethod
    def _parse_size_mb(value):
        if value in (None, ""):
            return 0

        match = re.match(r"^\s*([0-9.]+)\s*([KMGTPE]?)(?:i?B)?\s*$", str(value), re.IGNORECASE)
        if not match:
            return 0

        amount = float(match.group(1))
        unit = match.group(2).upper()
        factors = {
            "": 1,
            "K": 1 / 1024,
            "M": 1,
            "G": 1024,
            "T": 1024 * 1024,
            "P": 1024 * 1024 * 1024,
            "E": 1024 * 1024 * 1024 * 1024,
        }

        if not unit and amount > 1024 * 1024:
            return round(amount / 1024 / 1024)

        return round(amount * factors.get(unit, 1))

    @staticmethod
    def _normalize_mac(mac_address):
        if not mac_address:
            return None

        value = str(mac_address).strip().replace("-", ":").lower()
        parts = value.split(":")
        if len(parts) != 6:
            return None

        try:
            return ":".join(f"{int(part, 16):02x}" for part in parts)
        except ValueError:
            return None


class VMwareImporter:
    def __init__(self, endpoint, logger):
        self.endpoint = endpoint
        self.logger = logger
        self.include_pattern = re.compile(endpoint.include_name_regex) if endpoint.include_name_regex else None
        self.exclude_pattern = re.compile(endpoint.exclude_name_regex) if endpoint.exclude_name_regex else None
        self.provider_name = "Proxmox" if endpoint.provider == EndpointProviderChoices.PROVIDER_PROXMOX else "VMware"
        self.interface_content_type = None
        self.mac_address_content_type = None

    def sync(self):
        result = SyncResult()
        platforms = list(Platform.objects.all())
        self.interface_content_type = ContentType.objects.get_for_model(VMInterface)
        self.mac_address_content_type = ContentType.objects.get_for_model(VMInterface)
        client_class = ProxmoxClient if self.endpoint.provider == EndpointProviderChoices.PROVIDER_PROXMOX else VMwareClient

        with client_class(self.endpoint) as client:
            for vm_data in client.iter_virtual_machines():
                result.seen += 1

                if not self._should_sync_vm(vm_data):
                    result.skipped += 1
                    continue

                try:
                    with transaction.atomic():
                        self._sync_vm(vm_data, platforms, result)
                    result.synced += 1
                except Exception as exc:  # pragma: no cover - needs NetBox integration test
                    result.errors += 1
                    self.logger.error("Failed to synchronize VM %s: %s", vm_data.name, exc)

        return result

    def _should_sync_vm(self, vm_data):
        if self.include_pattern and not self.include_pattern.search(vm_data.name):
            return False
        if self.exclude_pattern and self.exclude_pattern.search(vm_data.name):
            return False
        if vm_data.status == "offline" and not self.endpoint.sync_powered_off:
            return False
        return True

    def _sync_vm(self, vm_data, platforms, result):
        nb_vm = VirtualMachine.objects.filter(
            name=vm_data.name,
            cluster=self.endpoint.cluster,
        ).first()

        created = nb_vm is None
        if created:
            nb_vm = VirtualMachine(
                name=vm_data.name,
                cluster=self.endpoint.cluster,
            )
        elif not self.endpoint.update_existing:
            result.skipped += 1
            return

        nb_vm.status = vm_data.status
        nb_vm.vcpus = vm_data.vcpus
        nb_vm.memory = vm_data.memory_mb
        nb_vm.tenant = self.endpoint.tenant
        nb_vm.platform = self._match_platform(vm_data.guest_os, platforms)

        if created or not nb_vm.virtualdisks.exists():
            nb_vm.disk = vm_data.disk_mb

        nb_vm.full_clean()
        nb_vm.save()

        if created:
            result.created += 1
            self.logger.info("Created VM %s", vm_data.name)
        else:
            result.updated += 1
            self.logger.info("Updated VM %s", vm_data.name)

        self._sync_virtual_disks(nb_vm, vm_data, result)

        if self.endpoint.sync_interfaces:
            primary_ipv4, primary_ipv6 = self._sync_interfaces(nb_vm, vm_data, result)
            self._set_primary_ips(nb_vm, primary_ipv4, primary_ipv6)

    @staticmethod
    def _match_platform(guest_os, platforms):
        if not guest_os:
            return None

        guest_os_lower = guest_os.lower()
        for platform in platforms:
            if platform.name.lower() in guest_os_lower:
                return platform

        return None

    def _sync_virtual_disks(self, nb_vm, vm_data, result):
        if not vm_data.disks:
            return

        synced_names = set()

        for disk_data in vm_data.disks:
            synced_names.add(disk_data.name)
            virtual_disk = VirtualDisk.objects.filter(
                virtual_machine=nb_vm,
                name=disk_data.name,
            ).first()
            created = virtual_disk is None

            if created:
                virtual_disk = VirtualDisk(
                    virtual_machine=nb_vm,
                    name=disk_data.name,
                )

            virtual_disk.size = disk_data.size_mb
            virtual_disk.description = disk_data.description
            virtual_disk.full_clean()
            virtual_disk.save()

            if created:
                result.virtual_disks_created += 1
                self.logger.info("Created virtual disk %s on %s", disk_data.name, nb_vm.name)
            else:
                result.virtual_disks_updated += 1
                self.logger.info("Updated virtual disk %s on %s", disk_data.name, nb_vm.name)

        stale_count = 0
        for description_prefix in (f"{self.provider_name}:",):
            stale_disks = VirtualDisk.objects.filter(
                virtual_machine=nb_vm,
                description__startswith=description_prefix,
            ).exclude(name__in=synced_names)
            stale_count += stale_disks.count()
            stale_disks.delete()

        if stale_count:
            result.virtual_disks_deleted += stale_count
            self.logger.info("Deleted %s stale %s virtual disk(s) from %s", stale_count, self.provider_name, nb_vm.name)

        disk_total = nb_vm.virtualdisks.aggregate(total=Sum("size", default=0))["total"] or vm_data.disk_mb
        if nb_vm.disk != disk_total:
            nb_vm.disk = disk_total
            nb_vm.full_clean()
            nb_vm.save(update_fields=("disk",))
            self.logger.info("Updated aggregate disk size for %s to %s MB", nb_vm.name, disk_total)

    def _sync_interfaces(self, nb_vm, vm_data, result):
        primary_ipv4 = None
        primary_ipv6 = None

        for interface_data in vm_data.interfaces:
            vm_interface = VMInterface.objects.filter(
                virtual_machine=nb_vm,
                name=interface_data.name,
            ).first()
            created = vm_interface is None

            if created:
                vm_interface = VMInterface(
                    virtual_machine=nb_vm,
                    name=interface_data.name,
                )

            vm_interface.enabled = True
            vm_interface.full_clean()
            vm_interface.save()

            if created:
                result.interfaces_created += 1
                self.logger.info("Created interface %s on %s", interface_data.name, nb_vm.name)
            else:
                result.interfaces_updated += 1
                self.logger.info("Updated interface %s on %s", interface_data.name, nb_vm.name)

            self._sync_mac_address(vm_interface, interface_data.mac_address, result)

            if not self.endpoint.sync_ip_addresses:
                continue

            for raw_ip in interface_data.ip_addresses:
                normalized = self._normalize_ip_address(raw_ip)
                if normalized is None:
                    continue

                address, family = normalized
                ip_obj = self._sync_ip_address(address, vm_interface, result)
                if ip_obj is None:
                    continue

                if family == 4 and primary_ipv4 is None:
                    primary_ipv4 = ip_obj
                if family == 6 and primary_ipv6 is None:
                    primary_ipv6 = ip_obj

        return primary_ipv4, primary_ipv6

    def _sync_mac_address(self, vm_interface, mac_address, result):
        normalized_mac = self._normalize_mac_address(mac_address)
        if normalized_mac is None:
            return None

        mac_obj = MACAddress.objects.filter(
            assigned_object_type=self.mac_address_content_type,
            assigned_object_id=vm_interface.pk,
            mac_address=normalized_mac,
        ).first()
        created = mac_obj is None

        if created:
            mac_obj = MACAddress(
                mac_address=normalized_mac,
                assigned_object=vm_interface,
            )

        mac_obj.description = f"{self.provider_name} reported MAC address"
        mac_obj.full_clean()
        mac_obj.save()

        if created:
            result.mac_addresses_created += 1
            self.logger.info("Created MAC address %s on interface %s", normalized_mac, vm_interface.name)
        else:
            result.mac_addresses_updated += 1
            self.logger.info("Updated MAC address %s on interface %s", normalized_mac, vm_interface.name)

        if vm_interface.primary_mac_address_id != mac_obj.pk:
            vm_interface.primary_mac_address = mac_obj
            vm_interface.full_clean()
            vm_interface.save(update_fields=("primary_mac_address",))
            self.logger.info("Set primary MAC address %s on interface %s", normalized_mac, vm_interface.name)

        stale_macs = MACAddress.objects.filter(
            assigned_object_type=self.mac_address_content_type,
            assigned_object_id=vm_interface.pk,
            description=f"{self.provider_name} reported MAC address",
        ).exclude(pk=mac_obj.pk)
        stale_count = stale_macs.count()
        if stale_count:
            stale_macs.delete()
            result.mac_addresses_deleted += stale_count
            self.logger.info("Deleted %s stale %s MAC address(es) from interface %s", stale_count, self.provider_name, vm_interface.name)

        return mac_obj

    @staticmethod
    def _normalize_mac_address(mac_address):
        if not mac_address:
            return None

        value = str(mac_address).strip().replace("-", ":").lower()
        parts = value.split(":")
        if len(parts) != 6:
            return None

        try:
            return ":".join(f"{int(part, 16):02x}" for part in parts)
        except ValueError:
            return None

    def _normalize_ip_address(self, raw_ip):
        if not raw_ip:
            return None

        raw_ip = str(raw_ip).split("%", 1)[0]

        try:
            if "/" in raw_ip:
                ip_interface = ipaddress.ip_interface(raw_ip)
                ip_obj = ip_interface.ip
                prefix_length = ip_interface.network.prefixlen
            else:
                ip_obj = ipaddress.ip_address(raw_ip)
                prefix_length = (
                    self.endpoint.default_ipv4_prefix_length
                    if ip_obj.version == 4
                    else self.endpoint.default_ipv6_prefix_length
                )
        except ValueError:
            return None

        if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_unspecified or ip_obj.is_multicast:
            return None

        return f"{ip_obj.compressed}/{prefix_length}", ip_obj.version

    def _sync_ip_address(self, address, vm_interface, result):
        existing_ip = IPAddress.objects.filter(address=address).first()

        if existing_ip and not self._may_update_ip(existing_ip, vm_interface):
            result.ip_conflicts += 1
            self.logger.warning(
                "Skipped IP %s because it belongs to another tenant or object.",
                address,
            )
            return None

        created = existing_ip is None
        ip_obj = existing_ip or IPAddress(address=address)
        ip_obj.status = "active"
        ip_obj.assigned_object = vm_interface

        if hasattr(ip_obj, "tenant"):
            ip_obj.tenant = self.endpoint.tenant

        ip_obj.full_clean()
        ip_obj.save()

        if created:
            result.ip_addresses_created += 1
            self.logger.info("Created IP %s", address)
        else:
            result.ip_addresses_updated += 1
            self.logger.info("Updated IP %s", address)

        return ip_obj

    def _may_update_ip(self, ip_obj, vm_interface):
        assigned_to_this_interface = (
            ip_obj.assigned_object_type_id == self.interface_content_type.id
            and ip_obj.assigned_object_id == vm_interface.pk
        )

        if assigned_to_this_interface:
            return True

        ip_tenant_id = getattr(ip_obj, "tenant_id", None)
        if self.endpoint.tenant_id and ip_tenant_id and ip_tenant_id != self.endpoint.tenant_id:
            return False

        if ip_obj.assigned_object_id and not assigned_to_this_interface:
            return False

        return True

    def _set_primary_ips(self, nb_vm, primary_ipv4, primary_ipv6):
        if not self.endpoint.sync_primary_ips:
            return

        update_fields = []
        if primary_ipv4 is not None:
            nb_vm.primary_ip4 = primary_ipv4
            update_fields.append("primary_ip4")
        if primary_ipv6 is not None:
            nb_vm.primary_ip6 = primary_ipv6
            update_fields.append("primary_ip6")

        if update_fields:
            nb_vm.full_clean()
            nb_vm.save(update_fields=update_fields)
            self.logger.info("Updated primary IPs for %s", nb_vm.name)
