from pyinfra import host
from pyinfra.operations import server, files


def prepare_k8s_node():
    """
    Prepares the OS for Kubernetes: Modules, Sysctl, Swap.
    """
    config = host.data.app_config.k8s
    modules = config.get("kernel_modules", [])
    sysctl_params = config.get("sysctl_params", {})

    # 1. Kernel Modules
    if modules:
        for mod in modules:
            server.modprobe(
                name=f"Load kernel module {mod}",
                module=mod,
            )

        # Persistence
        files.put(
            name="Persist kernel modules configuration",
            dest="/etc/modules-load.d/k8s.conf",
            content="\n".join(modules) + "\n",
        )

    # 2. Sysctl Params
    if sysctl_params:
        content = "\n".join([f"{k} = {v}" for k, v in sysctl_params.items()]) + "\n"
        files.put(
            name="Configure sysctl parameters",
            dest="/etc/sysctl.d/k8s.conf",
            content=content,
        )
        server.shell(
            name="Reload sysctl",
            commands=["sysctl --system"],
        )

    # 3. Disable Swap
    server.shell(
        name="Disable Swap (Runtime)",
        commands=["swapoff -a"],
    )

    # 4. Disable Swap in Fstab
    files.replace(
        name="Disable Swap (Fstab)",
        path="/etc/fstab",
        text=r"^([^#].*swap.*)$",
        replace=r"# \1 # Disabled by Calcifer",
    )

