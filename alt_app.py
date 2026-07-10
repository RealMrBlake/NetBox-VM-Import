import ssl
import atexit
import ipaddress
import tkinter as tk
from tkinter import ttk, messagebox

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import pynetbox

ssl._create_default_https_context = ssl._create_unverified_context


class ESXiNetBoxImporter:

    def __init__(self, root):
        self.root = root
        self.root.title("ESXi -> NetBox VM Synchronizer")
        self.root.geometry("950x750")

        self.si = None
        self.nb = None
        self.vms = []

        self.site_map = {}
        self.cluster_map = {}
        self.tenant_map = {}
        self.platforms = []

        self.create_gui()

    # =========================================================
    # GUI
    # =========================================================

    def create_gui(self):

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        # ============================================
        # ESXi / vCenter
        # ============================================

        ttk.Label(main, text="ESXi / vCenter Host").grid(
            row=0,
            column=0,
            sticky="w"
        )

        self.esxi_host = ttk.Entry(main, width=45)
        self.esxi_host.grid(row=0, column=1, sticky="ew")

        ttk.Label(main, text="Username").grid(
            row=1,
            column=0,
            sticky="w"
        )

        self.esxi_user = ttk.Entry(main, width=45)
        self.esxi_user.grid(row=1, column=1, sticky="ew")

        ttk.Label(main, text="Password").grid(
            row=2,
            column=0,
            sticky="w"
        )

        self.esxi_pass = ttk.Entry(main, width=45, show="*")
        self.esxi_pass.grid(row=2, column=1, sticky="ew")

        # ============================================
        # NetBox
        # ============================================

        ttk.Label(main, text="NetBox URL").grid(
            row=3,
            column=0,
            sticky="w"
        )

        self.nb_url = ttk.Entry(main, width=45)
        self.nb_url.grid(row=3, column=1, sticky="ew")

        ttk.Label(main, text="NetBox Token").grid(
            row=4,
            column=0,
            sticky="w"
        )

        self.nb_token = ttk.Entry(main, width=45, show="*")
        self.nb_token.grid(row=4, column=1, sticky="ew")

        ttk.Button(
            main,
            text="Verbinden & Daten laden",
            command=self.connect_all
        ).grid(
            row=5,
            column=1,
            sticky="e",
            pady=10
        )

        # ============================================
        # Zielauswahl
        # ============================================

        ttk.Label(main, text="Site").grid(
            row=6,
            column=0,
            sticky="w"
        )

        self.site_combo = ttk.Combobox(main, width=42)
        self.site_combo.grid(row=6, column=1, sticky="ew")

        ttk.Label(main, text="Cluster").grid(
            row=7,
            column=0,
            sticky="w"
        )

        self.cluster_combo = ttk.Combobox(main, width=42)
        self.cluster_combo.grid(row=7, column=1, sticky="ew")

        ttk.Label(main, text="Tenant").grid(
            row=8,
            column=0,
            sticky="w"
        )

        self.tenant_combo = ttk.Combobox(main, width=42)
        self.tenant_combo.grid(row=8, column=1, sticky="ew")

        # ============================================
        # VM Liste
        # ============================================

        ttk.Label(main, text="Gefundene VMs").grid(
            row=9,
            column=0,
            sticky="w",
            pady=(15, 5)
        )

        self.vm_list = tk.Listbox(
            main,
            selectmode=tk.MULTIPLE,
            width=100,
            height=25
        )

        self.vm_list.grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="nsew"
        )

        scrollbar = ttk.Scrollbar(
            main,
            orient="vertical",
            command=self.vm_list.yview
        )

        scrollbar.grid(row=10, column=2, sticky="ns")

        self.vm_list.config(yscrollcommand=scrollbar.set)

        # ============================================
        # Buttons
        # ============================================

        btn_frame = ttk.Frame(main)

        btn_frame.grid(
            row=11,
            column=0,
            columnspan=2,
            pady=10,
            sticky="e"
        )

        ttk.Button(
            btn_frame,
            text="Alle auswählen",
            command=self.select_all
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame,
            text="Import / Sync starten",
            command=self.import_vms
        ).pack(side="left", padx=5)

        # ============================================
        # Logfeld
        # ============================================

        ttk.Label(main, text="Log").grid(
            row=12,
            column=0,
            sticky="w"
        )

        self.log_text = tk.Text(main, height=10)

        self.log_text.grid(
            row=13,
            column=0,
            columnspan=2,
            sticky="nsew"
        )

        main.columnconfigure(1, weight=1)
        main.rowconfigure(10, weight=1)

    # =========================================================
    # Logging
    # =========================================================

    def log(self, text):

        self.log_text.insert(tk.END, f"{text}\n")
        self.log_text.see(tk.END)

        self.root.update()

    # =========================================================
    # Select All
    # =========================================================

    def select_all(self):

        self.vm_list.select_set(0, tk.END)

    # =========================================================
    # Verbindungen
    # =========================================================

    def connect_all(self):

        try:

            self.connect_esxi()
            self.connect_netbox()

            self.load_netbox_data()
            self.load_vms()

            messagebox.showinfo(
                "Erfolg",
                "Verbindung erfolgreich hergestellt"
            )

        except Exception as e:

            messagebox.showerror(
                "Fehler",
                str(e)
            )

    def connect_esxi(self):

        self.log("Verbinde zu ESXi/vCenter...")

        context = ssl._create_unverified_context()

        self.si = SmartConnect(
            host=self.esxi_host.get(),
            user=self.esxi_user.get(),
            pwd=self.esxi_pass.get(),
            sslContext=context
        )

        atexit.register(Disconnect, self.si)

        self.log("ESXi Verbindung erfolgreich")

    def connect_netbox(self):

        self.log("Verbinde zu NetBox...")

        self.nb = pynetbox.api(
            self.nb_url.get(),
            token=self.nb_token.get()
        )

        self.log("NetBox Verbindung erfolgreich")

    # =========================================================
    # NetBox Daten
    # =========================================================

    def load_netbox_data(self):

        self.log("Lade NetBox Daten...")

        # Sites
        sites = list(self.nb.dcim.sites.all())
        self.site_map = {x.name: x.id for x in sites}
        self.site_combo["values"] = list(self.site_map.keys())

        # Cluster
        clusters = list(self.nb.virtualization.clusters.all())
        self.cluster_map = {x.name: x.id for x in clusters}
        self.cluster_combo["values"] = list(self.cluster_map.keys())

        # Tenant
        tenants = list(self.nb.tenancy.tenants.all())
        self.tenant_map = {x.name: x.id for x in tenants}
        self.tenant_combo["values"] = list(self.tenant_map.keys())

        # Plattformen
        self.platforms = list(self.nb.dcim.platforms.all())

        self.log("NetBox Daten geladen")

    # =========================================================
    # VMware VMs laden
    # =========================================================

    def load_vms(self):

        self.log("Lade VMs aus VMware...")

        content = self.si.RetrieveContent()

        container = content.rootFolder

        view_type = [vim.VirtualMachine]

        recursive = True

        container_view = content.viewManager.CreateContainerView(
            container,
            view_type,
            recursive
        )

        self.vms = container_view.view

        self.vm_list.delete(0, tk.END)

        for vm in self.vms:
            self.vm_list.insert(tk.END, vm.name)

        self.log(f"{len(self.vms)} VMs gefunden")

    # =========================================================
    # Plattform Mapping
    # =========================================================

    def get_platform_id(self, guest_os):

        if not guest_os:
            return None

        guest_os = guest_os.lower()

        for platform in self.platforms:

            if platform.name.lower() in guest_os:
                return platform.id

        return None

    # =========================================================
    # Prefix automatisch ergänzen
    # =========================================================

    def get_ip_with_prefix(self, ip):

        try:

            addr = ipaddress.ip_address(ip)

            if addr.version == 4:
                return f"{ip}/24"

            return f"{ip}/64"

        except:
            return None

    # =========================================================
    # VM Import / Sync
    # =========================================================

    def import_vms(self):

        selected = self.vm_list.curselection()

        if not selected:

            messagebox.showwarning(
                "Hinweis",
                "Keine VMs ausgewählt"
            )

            return

        cluster_name = self.cluster_combo.get()
        tenant_name = self.tenant_combo.get()

        cluster_id = self.cluster_map.get(cluster_name)
        tenant_id = self.tenant_map.get(tenant_name)

        if not cluster_id:

            messagebox.showerror(
                "Fehler",
                "Bitte Cluster auswählen"
            )

            return

        for idx in selected:

            vm = self.vms[idx]

            self.log(f"Synchronisiere VM: {vm.name}")

            # ============================================
            # Hardwaredaten
            # ============================================

            memory = int(vm.config.hardware.memoryMB)

            vcpus = int(vm.config.hardware.numCPU)

            # ============================================
            # Disk in MB (NetBox >= 4.x)
            # ============================================

            disk_size = 0

            for dev in vm.config.hardware.device:

                if isinstance(dev, vim.vm.device.VirtualDisk):

                    # VMware liefert KB
                    # NetBox erwartet MB
                    size_mb = dev.capacityInKB / 1024

                    disk_size += round(size_mb)

            # ============================================
            # Betriebssystem
            # ============================================

            guest_os = ""

            try:
                guest_os = vm.config.guestFullName
            except:
                pass

            platform_id = self.get_platform_id(guest_os)

            # ============================================
            # Status
            # ============================================

            power_state = str(vm.runtime.powerState)

            if "poweredOn" in power_state:
                status = "active"
            else:
                status = "offline"

            # ============================================
            # VM Daten
            # ============================================

            vm_data = {
                "name": vm.name,
                "cluster": cluster_id,
                "status": status,
                "vcpus": vcpus,
                "memory": memory,
                "disk": disk_size,
                "tenant": tenant_id,
                "platform": platform_id
            }

            # ============================================
            # VM erstellen / aktualisieren
            # ============================================

            nb_vm = self.nb.virtualization.virtual_machines.get(
                name=vm.name
            )

            if nb_vm:

                nb_vm.update(vm_data)

                self.log(f"VM aktualisiert: {vm.name}")

            else:

                nb_vm = self.nb.virtualization.virtual_machines.create(
                    vm_data
                )

                self.log(f"VM erstellt: {vm.name}")

            # ============================================
            # Interfaces + IPs
            # ============================================

            primary_ipv4 = None
            primary_ipv6 = None

            if vm.guest and hasattr(vm.guest, "net"):

                for net in vm.guest.net:

                    mac = getattr(net, "macAddress", None)

                    if not mac:
                        continue

                    interface_name = getattr(net, "device", None)

                    if not interface_name:
                        interface_name = f"NIC-{mac[-5:]}"

                    iface_data = {
                        "virtual_machine": nb_vm.id,
                        "name": interface_name,
                        "mac_address": mac,
                        "enabled": True
                    }

                    # Interface zuerst über Namen suchen
                    existing_iface = self.nb.virtualization.interfaces.get(
                        virtual_machine_id=nb_vm.id,
                        name=interface_name
                    )

                    if existing_iface:

                        # Falls MAC geändert wurde -> aktualisieren
                        existing_iface.update(iface_data)

                        vm_iface = existing_iface

                        self.log(
                            f"Interface aktualisiert: {interface_name}"
                        )

                    else:

                        vm_iface = self.nb.virtualization.interfaces.create(
                            iface_data
                        )

                        self.log(
                            f"Interface erstellt: {interface_name}"
                        )

                    self.log(f"Interface synchronisiert: {mac}")

                    # ============================================
                    # IPs
                    # ============================================

                    if hasattr(net, "ipAddress"):

                        for ip in net.ipAddress:

                            if ip.startswith("127."):
                                continue

                            if ip == "::1":
                                continue

                            address = self.get_ip_with_prefix(ip)

                            if not address:
                                continue

                            existing_ip = self.nb.ipam.ip_addresses.get(
                                address=address
                            )

                            ip_data = {
                                "address": address,
                                "status": "active",
                                "assigned_object_type": "virtualization.vminterface",
                                "assigned_object_id": vm_iface.id
                            }

                            if existing_ip:

                                existing_ip.update(ip_data)

                                ip_obj = existing_ip

                                self.log(f"IP aktualisiert: {address}")

                            else:

                                ip_obj = self.nb.ipam.ip_addresses.create(
                                    ip_data
                                )

                                self.log(f"IP erstellt: {address}")

                            # ============================================
                            # Primary IP setzen
                            # ============================================

                            try:

                                parsed_ip = ipaddress.ip_address(ip)

                                if parsed_ip.version == 4:

                                    if not primary_ipv4:
                                        primary_ipv4 = ip_obj.id

                                else:

                                    if not primary_ipv6:
                                        primary_ipv6 = ip_obj.id

                            except:
                                pass

            # ============================================
            # Primäre IPs setzen
            # ============================================

            update_data = {}

            if primary_ipv4:
                update_data["primary_ip4"] = primary_ipv4

            if primary_ipv6:
                update_data["primary_ip6"] = primary_ipv6

            if update_data:

                nb_vm.update(update_data)

                self.log(
                    f"Primary IPs gesetzt für {vm.name}"
                )

        messagebox.showinfo(
            "Fertig",
            "VM Import / Synchronisierung abgeschlossen"
        )

        self.log("Synchronisierung abgeschlossen")


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = ESXiNetBoxImporter(root)

    root.mainloop()