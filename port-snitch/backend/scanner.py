"""Port scanner engine for macOS and Linux."""

import re
from models import PortEntry, RiskLevel, ServiceType

# Process name patterns -> ServiceType
SERVICE_PATTERNS: dict[str, ServiceType] = {
    r"postgres|psql": ServiceType.DATABASE,
    r"mysql|mariadb": ServiceType.DATABASE,
    r"mongo": ServiceType.DATABASE,
    r"redis": ServiceType.CACHE,
    r"memcache": ServiceType.CACHE,
    r"node|npm|deno|bun": ServiceType.HTTP,
    r"nginx|apache|httpd": ServiceType.HTTP,
    r"docker|containerd": ServiceType.UNKNOWN,
    r"sshd": ServiceType.SSH,
    r"rabbitmq|kafka": ServiceType.MESSAGE_QUEUE,
}

# Well-known ports -> ServiceType
PORT_SERVICES: dict[int, ServiceType] = {
    22: ServiceType.SSH,
    80: ServiceType.HTTP,
    443: ServiceType.HTTPS,
    3000: ServiceType.HTTP,
    3306: ServiceType.DATABASE,
    5432: ServiceType.DATABASE,
    6379: ServiceType.CACHE,
    27017: ServiceType.DATABASE,
    5672: ServiceType.MESSAGE_QUEUE,
    11211: ServiceType.CACHE,
}


def parse_lsof(output: str) -> list[PortEntry]:
    """Parse macOS lsof -iTCP -iUDP -nP output."""
    entries = []
    for line in output.strip().splitlines()[1:]:  # Skip header
        parts = line.split()
        if len(parts) < 9:
            continue
        process, pid, user = parts[0], parts[1], parts[2]
        proto_field = parts[7].lower()
        name_field = parts[8]

        protocol = "tcp" if "tcp" in proto_field else "udp"

        # Parse NAME field: "bind_addr:port" or "*:port"
        match = re.search(r"([\d.*]+|\*):(\d+)", name_field)
        if not match:
            continue
        bind_addr, port_str = match.groups()
        bind_addr = "0.0.0.0" if bind_addr == "*" else bind_addr

        try:
            entry = PortEntry(
                port=int(port_str),
                protocol=protocol,
                process=process,
                pid=int(pid),
                user=user,
                bind_address=bind_addr,
            )
            entries.append(entry)
        except (ValueError, Exception):
            continue
    return entries


def parse_ss(output: str) -> list[PortEntry]:
    """Parse Linux ss -tulnp output."""
    entries = []
    for line in output.strip().splitlines()[1:]:  # Skip header
        parts = line.split()
        if len(parts) < 6:
            continue

        proto = parts[0].lower().rstrip("6")  # tcp6 -> tcp
        if proto not in ("tcp", "udp"):
            continue

        local_addr = parts[4]
        # Parse "addr:port" format
        if ":" not in local_addr:
            continue
        bind_addr, port_str = local_addr.rsplit(":", 1)
        bind_addr = bind_addr.strip("[]") or "0.0.0.0"
        if bind_addr == "::":
            bind_addr = "0.0.0.0"

        # Parse process info: "users:(("name",pid=123,fd=4))"
        process, pid = "unknown", 0
        if len(parts) >= 7:
            proc_match = re.search(r'\("([^"]+)",pid=(\d+)', parts[6])
            if proc_match:
                process, pid = proc_match.group(1), int(proc_match.group(2))

        try:
            entry = PortEntry(
                port=int(port_str),
                protocol=proto,
                process=process,
                pid=pid,
                user="",
                bind_address=bind_addr,
            )
            entries.append(entry)
        except (ValueError, Exception):
            continue
    return entries


def detect_service_type(entry: PortEntry) -> ServiceType:
    """Detect service type from process name or port."""
    proc_lower = entry.process.lower()
    for pattern, svc_type in SERVICE_PATTERNS.items():
        if re.search(pattern, proc_lower):
            return svc_type
    return PORT_SERVICES.get(entry.port, ServiceType.UNKNOWN)


def identify_risks(entry: PortEntry) -> RiskLevel:
    """Identify risk level based on port and bind address."""
    is_privileged = entry.port < 1024
    is_public = entry.bind_address in ("0.0.0.0", "::", "*")

    if is_privileged and is_public:
        return RiskLevel.HIGH
    if is_public or is_privileged:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def generate_kill_command(entry: PortEntry) -> str:
    """Generate command to kill the process."""
    return f"kill -9 {entry.pid}"
