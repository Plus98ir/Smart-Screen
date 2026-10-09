"""Hardware + system metrics.

psutil gives CPU load, RAM, disks, network, processes on every OS.
On Windows, LibreHardwareMonitor (via pythonnet) adds temperatures, clocks, power, fans and GPU data.
If LHM is unavailable, nvidia-smi is used as a GPU fallback.
"""
import collections
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time

import psutil

from library.log import logger

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WINDOWS = platform.system() == "Windows"
NAN = math.nan
HISTORY = 90  # samples kept for graphs (1 per second)

VIRTUAL_NIC = re.compile(r"loopback|vethernet|vmware|virtualbox|vbox|hyper-v|bluetooth|teredo|isatap|"
                         r"pseudo|npcap|docker|wsl|^lo$", re.I)


def is_admin() -> bool:
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def short_cpu_name(name: str) -> str:
    n = re.sub(r"\((R|TM|tm|r)\)", "", name)
    n = re.sub(r"\s+CPU\s*@.*$", "", n)
    n = re.sub(r"\s+\d+-Core Processor.*$", "", n)
    n = re.sub(r"\s+(Processor|with Radeon.*)$", "", n)
    n = n.replace("Intel ", "").replace("AMD ", "").replace("  ", " ").strip()
    return n or name


def short_gpu_name(name: str) -> str:
    n = name.replace("NVIDIA ", "").replace("GeForce ", "").replace("AMD ", "").replace("Radeon(TM) ", "Radeon ")
    n = n.replace("Intel(R) ", "").replace("Graphics", "Gfx").strip()
    return n or name


def cpu_name() -> str:
    if IS_WINDOWS:
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except Exception:
            pass
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "CPU"


class LHM:
    """Thin wrapper around LibreHardwareMonitorLib.dll."""

    def __init__(self):
        dll_dir = os.path.join(APP_DIR, "external", "LibreHardwareMonitor")
        import clr  # pythonnet
        clr.AddReference(os.path.join(dll_dir, "LibreHardwareMonitorLib.dll"))
        clr.AddReference(os.path.join(dll_dir, "HidSharp.dll"))
        from LibreHardwareMonitor import Hardware  # noqa
        self.H = Hardware
        c = Hardware.Computer()
        c.IsCpuEnabled = True
        c.IsGpuEnabled = True
        c.IsMemoryEnabled = False
        c.IsMotherboardEnabled = True
        c.IsControllerEnabled = True
        c.IsNetworkEnabled = False
        c.IsStorageEnabled = False  # SMART reads are slow; drive temps are not shown
        c.IsPsuEnabled = False
        c.Open()
        self.c = c
        self.gpu = self._pick_gpu()
        for hw in c.Hardware:
            logger.info("LHM found: %s (%s)", hw.Name, hw.HardwareType)

    def _pick_gpu(self):
        T = self.H.HardwareType
        gpus = [h for h in self.c.Hardware if h.HardwareType in (T.GpuNvidia, T.GpuAmd, T.GpuIntel)]
        for kind in (T.GpuNvidia, T.GpuAmd, T.GpuIntel):
            for g in gpus:
                if g.HardwareType == kind:
                    if kind == T.GpuAmd and len([x for x in gpus if x.HardwareType == T.GpuAmd]) > 1:
                        # skip the iGPU of an APU: the discrete card reports dedicated memory
                        g.Update()
                        if not any(str(s.Name) == "GPU Memory Total" for s in g.Sensors):
                            continue
                    return g
        return gpus[0] if gpus else None

    @staticmethod
    def _val(sensors, stype, *prefixes, contains=None, exclude=None):
        for p in prefixes:
            for s in sensors:
                n = str(s.Name)
                if s.SensorType == stype and s.Value is not None and n.startswith(p):
                    if contains and contains not in n:
                        continue
                    if exclude and exclude in n:
                        continue
                    return float(s.Value)
        return NAN

    def read(self) -> dict:
        S = self.H.SensorType
        T = self.H.HardwareType
        out = {}
        for hw in self.c.Hardware:
            if hw.HardwareType == T.Cpu:
                hw.Update()
                s = list(hw.Sensors)
                out["cpu_temp"] = self._val(s, S.Temperature, "Core Average", "Core Max", "CPU Package",
                                            "Core (Tctl/Tdie)", "Tctl", "Tdie", "CCD", "Core")
                clocks = [float(x.Value) for x in s if x.SensorType == S.Clock and x.Value is not None
                          and "Core #" in str(x.Name) and "Effective" not in str(x.Name)]
                if not clocks:
                    clocks = [float(x.Value) for x in s if x.SensorType == S.Clock and x.Value is not None
                              and "Core #" in str(x.Name)]
                out["cpu_clock"] = max(clocks) if clocks else NAN
                out["cpu_power"] = self._val(s, S.Power, "Package", "CPU Package", "Core (SVI2 TFN)")
            elif hw.HardwareType == T.Motherboard:
                hw.Update()
                fans = []
                for sub in hw.SubHardware:
                    sub.Update()
                    for x in sub.Sensors:
                        if x.SensorType == S.Fan and x.Value is not None and float(x.Value) > 0:
                            fans.append((str(x.Name), float(x.Value)))
                out["fans"] = fans
        g = self.gpu
        if g is not None:
            g.Update()
            s = list(g.Sensors)
            load = self._val(s, S.Load, "GPU Core")
            if math.isnan(load):
                load = self._val(s, S.Load, "D3D 3D")
            used = self._val(s, S.SmallData, "GPU Memory Used")
            if math.isnan(used):
                used = self._val(s, S.SmallData, "D3D Dedicated Memory Used")
            total = self._val(s, S.SmallData, "GPU Memory Total")
            if math.isnan(total):
                total = self._val(s, S.SmallData, "D3D Dedicated Memory Total")
            out.update({
                "gpu_name": str(g.Name),
                "gpu_load": load,
                "gpu_temp": self._val(s, S.Temperature, "GPU Core", "GPU Hot Spot", "GPU"),
                "gpu_hotspot": self._val(s, S.Temperature, "GPU Hot Spot"),
                "gpu_clock": self._val(s, S.Clock, "GPU Core"),
                "gpu_power": self._val(s, S.Power, "GPU Package", "GPU Power", "GPU Core", "GPU"),
                "gpu_mem_used": used,    # MB
                "gpu_mem_total": total,  # MB
                "gpu_fan": self._val(s, S.Fan, "GPU Fan", "GPU"),
                "gpu_fan_pct": self._val(s, S.Control, "GPU Fan", "GPU"),
            })
        return out

    def close(self):
        try:
            self.c.Close()
        except Exception:
            pass


class NvidiaSmi:
    """Fallback GPU reader when LHM is not available."""
    FIELDS = "name,utilization.gpu,temperature.gpu,clocks.gr,power.draw,memory.used,memory.total,fan.speed"

    def __init__(self):
        self.exe = shutil.which("nvidia-smi")
        if not self.exe:
            raise RuntimeError("nvidia-smi not found")

    def read(self) -> dict:
        flags = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW
        r = subprocess.run([self.exe, f"--query-gpu={self.FIELDS}", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=3, creationflags=flags)
        p = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]

        def f(v):
            try:
                return float(v)
            except ValueError:
                return NAN
        return {"gpu_name": p[0], "gpu_load": f(p[1]), "gpu_temp": f(p[2]), "gpu_clock": f(p[3]),
                "gpu_power": f(p[4]), "gpu_mem_used": f(p[5]), "gpu_mem_total": f(p[6]), "gpu_fan_pct": f(p[7])}


class Stats:
    """Collects a metrics snapshot every second in a background thread."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.data = {}
        self.hist = collections.defaultdict(lambda: collections.deque([0.0] * HISTORY, maxlen=HISTORY))
        self.hw = None
        self.gpu_fallback = None
        self.cpu_full = cpu_name()
        self.host = socket.gethostname()
        self._prev_net = None
        self._prev_disk = None
        self._prev_t = None
        self._procs = []
        self._procs_t = 0
        self._stop = threading.Event()
        self.admin = is_admin()
        self._init_hw()
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)

    def _init_hw(self):
        if IS_WINDOWS and self.cfg.get("sensors", "use_lhm", default=True):
            try:
                self.hw = LHM()
                if not self.admin:
                    logger.warning("Not running as administrator: temperatures may be missing")
            except Exception as e:
                logger.warning("LibreHardwareMonitor unavailable: %s", e)
                self.hw = None
        if self.hw is None or getattr(self.hw, "gpu", None) is None:
            try:
                self.gpu_fallback = NvidiaSmi()
            except Exception:
                self.gpu_fallback = None

    # ---------------------------------------------------------------- helpers
    def _pick_nic(self, counters, stats):
        want = self.cfg.get("network", "interface", default="auto")
        if want and want != "auto" and want in counters:
            return want
        vpn_pat = [p.lower() for p in self.cfg.get("network", "vpn_adapters", default=[])]
        best, best_bytes = None, -1
        for name, c in counters.items():
            st = stats.get(name)
            if not st or not st.isup or VIRTUAL_NIC.search(name):
                continue
            if any(p in name.lower() for p in vpn_pat):
                continue  # count the physical link; VPN traffic also passes through it
            total = c.bytes_recv + c.bytes_sent
            if total > best_bytes:
                best, best_bytes = name, total
        return best

    def vpn_adapter(self, stats=None):
        stats = stats or psutil.net_if_stats()
        pats = [p.lower() for p in self.cfg.get("network", "vpn_adapters", default=[])]
        for name, st in stats.items():
            if st.isup and any(p in name.lower() for p in pats):
                return name
        return None

    def _top_processes(self):
        now = time.time()
        if now - self._procs_t < 3:
            return self._procs
        self._procs_t = now
        ncpu = psutil.cpu_count() or 1
        rows = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                name = p.info["name"] or ""
                if name in ("System Idle Process", "Idle", "System", "Registry", "Memory Compression"):
                    continue
                cpu = p.cpu_percent(None) / ncpu
                mem = p.info["memory_info"].rss if p.info["memory_info"] else 0
                rows.append((name, cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # merge processes with the same name (chrome.exe x40)
        merged = {}
        for name, cpu, mem in rows:
            m = merged.setdefault(name, [0.0, 0])
            m[0] += cpu
            m[1] += mem
        procs = [(re.sub(r"\.exe$", "", n, flags=re.I), c, m) for n, (c, m) in merged.items()]
        self._procs = {"cpu": sorted(procs, key=lambda x: -x[1])[:5],
                       "mem": sorted(procs, key=lambda x: -x[2])[:5]}
        return self._procs

    # ---------------------------------------------------------------- sampling
    def sample(self):
        now = time.time()
        d = {"time": now, "host": self.host, "admin": self.admin}
        d["cpu_name"] = self.cfg.get("sensors", "cpu_label") or short_cpu_name(self.cpu_full)
        d["cpu_load"] = psutil.cpu_percent(None)
        d["cpu_cores"] = psutil.cpu_percent(None, percpu=True)
        d["cpu_count"] = psutil.cpu_count(logical=False) or 0
        d["cpu_threads"] = psutil.cpu_count() or 0
        try:
            d["cpu_clock"] = float(psutil.cpu_freq().current)
        except Exception:
            d["cpu_clock"] = NAN
        vm = psutil.virtual_memory()
        d["ram_pct"], d["ram_used"], d["ram_total"] = vm.percent, vm.total - vm.available, vm.total
        d["boot"] = psutil.boot_time()

        # hardware sensors
        hw = {}
        if self.hw is not None:
            try:
                hw = self.hw.read()
            except Exception as e:
                logger.warning("LHM read failed: %s", e)
        if self.gpu_fallback is not None and "gpu_load" not in hw:
            try:
                hw.update(self.gpu_fallback.read())
            except Exception:
                pass
        for k, v in hw.items():
            if k == "cpu_clock" and (v is None or (isinstance(v, float) and math.isnan(v))):
                continue
            d[k] = v
        if "gpu_name" in d:
            d["gpu_short"] = self.cfg.get("sensors", "gpu_label") or short_gpu_name(d["gpu_name"])

        # network
        counters = psutil.net_io_counters(pernic=True)
        stats = psutil.net_if_stats()
        nic = self._pick_nic(counters, stats)
        d["nic"] = nic
        d["vpn_adapter"] = self.vpn_adapter(stats)
        dt = (now - self._prev_t) if self._prev_t else 1.0
        down = up = 0.0
        if nic and nic in counters:
            c = counters[nic]
            if self._prev_net and self._prev_net[0] == nic:
                down = max(0.0, (c.bytes_recv - self._prev_net[1]) / dt)
                up = max(0.0, (c.bytes_sent - self._prev_net[2]) / dt)
            self._prev_net = (nic, c.bytes_recv, c.bytes_sent)
            d["net_total_down"], d["net_total_up"] = c.bytes_recv, c.bytes_sent
        d["net_down"], d["net_up"] = down, up

        # disks
        try:
            io = psutil.disk_io_counters()
            rd = wr = 0.0
            if io and self._prev_disk:
                rd = max(0.0, (io.read_bytes - self._prev_disk[0]) / dt)
                wr = max(0.0, (io.write_bytes - self._prev_disk[1]) / dt)
            if io:
                self._prev_disk = (io.read_bytes, io.write_bytes)
            d["disk_read"], d["disk_write"] = rd, wr
        except Exception:
            d["disk_read"] = d["disk_write"] = 0.0
        disks = []
        for p in psutil.disk_partitions(all=False):
            if IS_WINDOWS and ("cdrom" in p.opts or not p.fstype):
                continue
            if not IS_WINDOWS and p.mountpoint.startswith(("/snap", "/boot", "/proc", "/sys", "/run")):
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
            except Exception:
                continue
            label = p.device.rstrip("\\") if IS_WINDOWS else p.mountpoint
            disks.append({"label": label, "used": u.used, "total": u.total, "pct": u.percent})
        d["disks"] = disks[:6]
        d["procs"] = self._top_processes()
        self._prev_t = now

        with self.lock:
            self.data = d
            for key in ("cpu_load", "gpu_load", "ram_pct", "net_down", "net_up", "cpu_temp", "gpu_temp",
                        "disk_read", "disk_write"):
                v = d.get(key, 0.0)
                self.hist[key].append(0.0 if v is None or (isinstance(v, float) and math.isnan(v)) else float(v))

    def run(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self.sample()
            except Exception as e:
                logger.exception("Sampling failed: %s", e)
            self._stop.wait(max(0.2, 1.0 - (time.time() - t0)))

    def start(self):
        threading.Thread(target=self.run, name="stats", daemon=True).start()

    def stop(self):
        self._stop.set()
        if self.hw:
            self.hw.close()

    def snapshot(self):
        with self.lock:
            return dict(self.data), {k: list(v) for k, v in self.hist.items()}
