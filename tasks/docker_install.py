from io import StringIO

from pyinfra import host
from pyinfra.facts.server import LinuxDistribution
from pyinfra.operations import apt, server, files, systemd

from utils.logger import log_operation


@log_operation
def install_docker():
    """
    Installs Docker Engine on Ubuntu following the official guide.
    """
    config = host.data.app_config.docker

    # 1. Uninstall old versions
    # The guide lists these packages to remove.
    apt.packages(
        name="Remove conflicting Docker packages",
        packages=config.old_packages,
        present=False,
    )

    # 2. Set up Docker's apt repository
    # 2.1 Install prerequisites
    apt.packages(
        name="Install Docker prerequisites",
        packages=["ca-certificates", "curl"],
        update=True,
    )

    # 2.2 Create keyrings directory
    files.directory(
        name="Ensure /etc/apt/keyrings exists",
        path="/etc/apt/keyrings",
        mode="755",
    )

    # 2.3 Download GPG key
    # Guide: sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    # We use server.shell to replicate the curl command exactly as it handles the download cleanly.
    server.shell(
        name="Download Docker GPG key",
        commands=[
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc",
            "chmod a+r /etc/apt/keyrings/docker.asc",
        ],
    )

    # 2.4 Add the repository to Apt sources
    # Guide uses the deb822 format in /etc/apt/sources.list.d/docker.sources

    # We need the codename (e.g., jammy, noble). 
    # host.get_fact(LinuxDistribution) returns a dict with 'codename'
    distro_codename = host.get_fact(LinuxDistribution)["release_meta"]["VERSION_CODENAME"]

    docker_sources_content = f"""Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: {distro_codename}
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
"""

    files.put(
        name="Create /etc/apt/sources.list.d/docker.sources",
        src=StringIO(docker_sources_content),
        dest="/etc/apt/sources.list.d/docker.sources",
        mode="644",
    )

    # 2.5 Update apt cache (required after adding new source)
    apt.update(
        name="Update Apt cache",
    )

    # 3. Install Docker packages
    apt.packages(
        name="Install Docker Engine and plugins",
        packages=config.install_packages,
    )

    # 4. Verify/Ensure services are running and enabled
    # https://docs.docker.com/engine/install/linux-postinstall/#configure-docker-to-start-on-boot-with-systemd
    for service_name in ["docker", "containerd"]:
        systemd.service(
            name=f"Ensure {service_name} service is running and enabled",
            service=service_name,
            running=True,
            enabled=True,
        )

    # 5. Manage Docker as a non-root user
    # https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user
    server.group(
        name="Ensure docker group exists",
        group="docker",
        present=True,
    )

    user = host.data.get("ssh_user")
    if user:
        server.shell(
            name=f"Add user {user} to docker group",
            commands=[f"usermod -aG docker {user}"],
        )
