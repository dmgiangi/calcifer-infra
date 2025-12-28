from pyinfra import host
from pyinfra.operations import server, files


def set_hostname_and_hosts():
    """
    Configures the system hostname and /etc/hosts file.
    """
    # In Pyinfra, host.name refers to the inventory name or hostname
    # We use the inventory name from hosts.yaml
    target_hostname = host.data.get("hostname") or host.name

    server.hostname(
        name=f"Set System Hostname to {target_hostname}",
        hostname=target_hostname,
    )

    files.line(
        name="Ensure localhost in /etc/hosts",
        path="/etc/hosts",
        line="127.0.0.1 localhost",
        replace="^127\\.0\\.0\\.1\\s+localhost",
    )

    files.line(
        name=f"Ensure {target_hostname} resolution in /etc/hosts",
        path="/etc/hosts",
        line=f"127.0.1.1 {target_hostname}",
        replace="^127\\.0\\.1\\.1\\s+",
    )