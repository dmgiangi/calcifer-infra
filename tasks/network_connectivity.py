from pyinfra.operations import server

from utils.logger import log_operation


@log_operation
def check_internet_access():
    """
    Verifies if the host can reach the internet (Ping 1.1.1.1).
    """
    server.shell(
        name="Check Internet Connectivity",
        commands=["ping -c 2 1.1.1.1"]
    )