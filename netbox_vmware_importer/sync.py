import ipaddress
import re
import ssl
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from dcim.models import Platform
from ipam.models import IPAddress
from virtualization.models import VMInterface, VirtualMachine

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
class VMData:
    name: str
    status: str
    vcpus: int
    memory_mb: int
    disk_mb: int
    guest_os: str = ""
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
        disk_mb = self._get_disk_size_mb(hardware)
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
            interfaces=self._get_interfaces(vm_obj),
        )

    @staticmethod
    def _get_disk_size_mb(hardware):
        disk_mb = 0
        for device in getattr(hardware, "device", []) or []:
            if isinstance(device, vim.vm.device.VirtualDisk):
                disk_mb += round((device.capacityInKB or 0) / 1024)
        return disk_mb

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
        self.interface_content_type = None

    def sync(self):
        result = SyncResult()
        platforms = list(Platform.objects.all())
        self.interface_content_type = ContentType.objects.get_for_model(VMInterface)

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
        nb_vm.disk = vm_data.disk_mb
        nb_vm.tenant = self.endpoint.tenant
        nb_vm.platform = self._match_platform(vm_data.guest_os, platforms)

        nb_vm.full_clean()
        nb_vm.save()

        if created:
            result.created += 1
            self.logger.info("Created VM %s", vm_data.name)
        else:
            result.updated += 1
            self.logger.info("Updated VM %s", vm_data.name)

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

            vm_interface.mac_address = interface_data.mac_address
            vm_interface.enabled = True
            vm_interface.full_clean()
            vm_interface.save()

            if created:
                result.interfaces_created += 1
                self.logger.info("Created interface %s on %s", interface_data.name, nb_vm.name)
            else:
                result.interfaces_updated += 1
                self.logger.info("Updated interface %s on %s", interface_data.name, nb_vm.name)

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
