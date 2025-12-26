class RuntimeConfig:
    """
    Singleton class to hold global runtime configurations.
    """
    # Changed Default: True (Verbose by default)
    VERBOSE: bool = True
    CONFIG_FILE: str = "cluster_config.yaml"

config = RuntimeConfig()