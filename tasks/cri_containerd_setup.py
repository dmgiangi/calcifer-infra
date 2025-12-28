from pyinfra.operations import apt, server, files, systemd


def install_containerd():
    """
    Install & Configure Containerd.
    """
    # 1. Dependencies
    apt.packages(
        name="Install Containerd Dependencies",
        packages=["ca-certificates", "curl", "gnupg"],
        update=True,
    )

    # 2. Add Docker Repo
    apt.key(
        name="Add Docker Apt Key",
        src="https://download.docker.com/linux/ubuntu/gpg",
    )

    apt.repo(
        name="Add Docker Apt Repo",
        src="deb [arch=amd64] https://download.docker.com/linux/ubuntu jammy stable",
        filename="docker",
    )

    # 3. Install Containerd
    apt.packages(
        name="Install Containerd",
        packages=["containerd.io"],
        update=True,
    )

    # 4. Configure
    files.directory(
        name="Ensure /etc/containerd exists",
        path="/etc/containerd",
    )

    # Generate default config if missing
    server.shell(
        name="Generate default config.toml",
        commands=["containerd config default > /etc/containerd/config.toml"],
    )

    # Patch Config
    files.replace(
        name="Enable SystemdCgroup",
        path="/etc/containerd/config.toml",
        text=r"SystemdCgroup = false",
        replace="SystemdCgroup = true",
    )

    # 5. Restart
    systemd.service(
        name="Restart Containerd",
        service="containerd",
        running=True,
        enabled=True,
        restarted=True,
    )