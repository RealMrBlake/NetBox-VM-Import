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

from .choices import EndpointProviderChoices

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


class VMwareImporter:
    def __init__(self, endpoint, logger):
        self.endpoint = endpoint
        self.logger = logger
        self.include_pattern = re.compile(endpoint.include_name_regex) if endpoint.include_name_regex else None
        self.exclude_pattern = re.compile(endpoint.exclude_name_regex) if endpoint.exclude_name_regex else None
        self.provider_name = "VMware"
        self.interface_content_type = None
        self.mac_address_content_type = None

    def sync(self):
        if self.endpoint.provider != EndpointProviderChoices.PROVIDER_VMWARE:
            raise VMwareConnectionError("Legacy Proxmox endpoints are no longer supported. Delete this endpoint.")

        result = SyncResult()
        platforms = list(Platform.objects.all())
        self.interface_content_type = ContentType.objects.get_for_model(VMInterface)
        self.mac_address_content_type = ContentType.objects.get_for_model(VMInterface)

        with VMwareClient(self.endpoint) as client:
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
