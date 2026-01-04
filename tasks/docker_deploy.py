import json
import os
from io import StringIO

from dotenv import dotenv_values
from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import files

from utils.logger import log_operation


@log_operation
def deploy_docker_app():
    """
    Deploys application files defined in assets.json.
    Configuration is loaded from host.data.app_config.docker.
    """
    config = host.data.app_config.docker
    source_path = config.source_path

    # Paths to configuration files
    assets_file_path = os.path.join(source_path, "assets.json")
    env_file_path = os.path.join(source_path, ".env")

    # Load environment variables for substitution
    env_vars = {}
    if os.path.exists(env_file_path):
        env_vars = dotenv_values(env_file_path)

    # Load assets definition
    if not os.path.exists(assets_file_path):
        print(f"Warning: {assets_file_path} not found. Skipping file deployment.")
        return

    with open(assets_file_path, "r") as f:
        assets = json.load(f)

    ssh_user = host.data.get("ssh_user")

    for asset in assets:
        file_rel_path = asset.get("file")
        dest_path = asset.get("dest")
        mode = asset.get("mode", "600")
        overwrite = asset.get("overwrite", False)
        substitute_secrets = asset.get("substitute_secrets", False)

        src_file_path = os.path.join(source_path, file_rel_path)

        # 1. Check overwrite policy
        if not overwrite:
            # If the file exists on the remote host, skip it
            remote_file = host.get_fact(File, path=dest_path)
            if remote_file:
                continue

        # 2. Ensure parent directory exists
        parent_dir = os.path.dirname(dest_path)
        files.directory(
            name=f"Ensure directory exists: {parent_dir}",
            path=parent_dir,
            user=ssh_user,
            group=ssh_user,
            mode="755",
        )

        # 3. Prepare content (Read + Substitute)
        if not os.path.exists(src_file_path):
            print(f"Warning: Source file {src_file_path} not found. Skipping.")
            continue

        with open(src_file_path, "r") as f:
            content = f.read()

        if substitute_secrets:
            for key, value in env_vars.items():
                if value is not None:
                    content = content.replace(f"§§§{key}§§§", value)

        # 4. Upload file
        files.put(
            name=f"Deploy file {file_rel_path} to {dest_path}",
            src=StringIO(content),
            dest=dest_path,
            user=ssh_user,
            group=ssh_user,
            mode=mode,
        )
