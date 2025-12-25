class RuntimeConfig:
    """
    Singleton class to hold global runtime configurations
    set via CLI arguments (like --verbose).
    """
    VERBOSE: bool = False


config = RuntimeConfig()
