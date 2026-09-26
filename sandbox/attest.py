"""Sandbox self-attestation. Baked into the image at /opt/attest.py.

Runs as the sandbox user when the sandbox starts and prints one JSON object
describing what the code inside can and cannot do. The control plane stores it
and the UI renders it as the "Blast radius" panel.
"""

import json
import os
import platform
import socket
import sys


def read(path, limit=4096):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(limit)
    except Exception as exc:
        return None if isinstance(exc, FileNotFoundError) else f"<unreadable: {type(exc).__name__}>"


def status_field(name):
    for line in (read("/proc/self/status") or "").splitlines():
        if line.startswith(name + ":"):
            return line.split(":", 1)[1].strip()
    return None


def interfaces():
    names = set()
    try:
        names.update(os.listdir("/sys/class/net"))
    except Exception:
        pass
    try:
        names.update(n for _, n in socket.if_nameindex())
    except Exception:
        pass
    dev = read("/proc/net/dev") or ""
    for line in dev.splitlines()[2:]:
        if ":" in line:
            names.add(line.split(":", 1)[0].strip())
    return sorted(names)


def try_connect(host, port):
    try:
        s = socket.create_connection((host, port), timeout=3)
        s.close()
        return True, "connected"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def try_dns(name):
    try:
        socket.getaddrinfo(name, 443)
        return True, "resolved"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def try_write(directory):
    probe = os.path.join(directory, ".attest_probe")
    try:
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return True, "write succeeded"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc.strerror if hasattr(exc, 'strerror') and exc.strerror else exc}"


def cgroup_limits():
    out = {}
    v2 = {"memory_max": "/sys/fs/cgroup/memory.max", "cpu_max": "/sys/fs/cgroup/cpu.max", "pids_max": "/sys/fs/cgroup/pids.max"}
    v1 = {
        "memory_max": "/sys/fs/cgroup/memory/memory.limit_in_bytes",
        "cpu_quota_us": "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
        "cpu_period_us": "/sys/fs/cgroup/cpu/cpu.cfs_period_us",
        "pids_max": "/sys/fs/cgroup/pids/pids.max",
    }
    for table in (v2, v1):
        for k, p in table.items():
            v = read(p, 128)
            if v is not None and not v.startswith("<"):
                out.setdefault(k, v.strip())
    return out


def mounts():
    rows = []
    for line in (read("/proc/self/mounts", 65536) or "").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] in ("/", "/in", "/work", "/out", "/tmp"):
            opts = parts[3].split(",")
            rows.append({"target": parts[1], "fstype": parts[2], "mode": "ro" if "ro" in opts else "rw"})
    return rows


def main():
    cap_eff = status_field("CapEff") or ""
    try:
        cap_int = int(cap_eff, 16)
    except ValueError:
        cap_int = -1
    ifaces = interfaces()
    out_ok, out_detail = try_connect("1.1.1.1", 443)
    out2_ok, out2_detail = try_connect("169.254.169.254", 80)
    dns_ok, dns_detail = try_dns("example.com")
    root_w, root_detail = try_write("/")
    in_w, in_detail = try_write("/in")
    work_w, work_detail = try_write("/work")
    out_w, outw_detail = try_write("/out")
    tmp_w, tmp_detail = try_write("/tmp")
    env_names = sorted(os.environ.keys())
    secretish = [n for n in env_names if any(k in n.upper() for k in ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "CRED", "AWS", "DATABASE"))]
    version = (read("/proc/version") or "").strip()
    try:
        in_files = sorted(os.listdir("/in"))
    except Exception:
        in_files = []

    checks = [
        {"id": "network_interfaces", "ok": set(ifaces) <= {"lo"}, "label": "Only loopback network interface",
         "detail": ", ".join(ifaces) or "none"},
        {"id": "egress_blocked", "ok": not out_ok and not out2_ok, "label": "Outbound connections fail",
         "detail": f"1.1.1.1:443 -> {out_detail}; metadata 169.254.169.254:80 -> {out2_detail}"},
        {"id": "dns_blocked", "ok": not dns_ok, "label": "DNS resolution fails", "detail": dns_detail},
        {"id": "rootfs_readonly", "ok": not root_w, "label": "Root filesystem is read-only", "detail": root_detail},
        {"id": "inputs_readonly", "ok": not in_w, "label": "Inputs (/in) are read-only", "detail": in_detail},
        {"id": "work_writable", "ok": work_w, "label": "Scratch space (/work) is writable", "detail": work_detail},
        {"id": "out_writable", "ok": out_w, "label": "Outputs (/out) are writable", "detail": outw_detail},
        {"id": "non_root", "ok": os.getuid() != 0 and os.geteuid() != 0, "label": f"Runs as uid {os.getuid()}, not root",
         "detail": f"uid={os.getuid()} gid={os.getgid()} groups={os.getgroups()}"},
        {"id": "no_capabilities", "ok": cap_int == 0, "label": "No Linux capabilities", "detail": f"CapEff={cap_eff}"},
        {"id": "no_new_privs", "ok": status_field("NoNewPrivs") == "1", "label": "No privilege escalation (no_new_privs)",
         "detail": f"NoNewPrivs={status_field('NoNewPrivs')}"},
        {"id": "no_secrets_in_env", "ok": not secretish, "label": "No secrets in the environment",
         "detail": "variable names: " + ", ".join(env_names)},
        {"id": "gvisor_kernel", "ok": "gvisor" in version.lower() or "4.4.0 #1" in version, "label": "Kernel is gVisor's user-space kernel",
         "detail": version[:160]},
    ]
    build = read("/etc/image-build.json")
    try:
        build = json.loads(build) if build else None
    except ValueError:
        pass
    report = {
        "schema": "tieout.attestation.v1",
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "facts": {
            "uid": os.getuid(), "gid": os.getgid(), "cap_eff": cap_eff, "interfaces": ifaces, "env_names": env_names,
            "kernel": version, "platform": platform.platform(), "python": sys.version.split()[0],
            "cgroup": cgroup_limits(), "mounts": mounts(), "in_files": in_files, "image_build": build,
            "cpu_count_visible": os.cpu_count(), "hostname": socket.gethostname(),
        },
    }
    print(json.dumps(report))


if __name__ == "__main__":
    main()
