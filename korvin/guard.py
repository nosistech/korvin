"""Block network use with every computer except this one.

Python calls the guard before it does these socket actions:
- connect, and sendto: the guard allows only a loopback IP address.
- bind: the guard allows only a loopback IP address, so Korvin cannot listen for other devices.
- getaddrinfo (a name lookup): the guard allows only localhost, a loopback IP address, or no host.
For these actions, the guard refuses every other address or host. Once the guard is on, it stays on until Python stops.

The guard protects against mistakes in Korvin's code and in the Python libraries it uses.
It is not a sandbox. It does not check other socket actions, such as the older name lookups
(gethostbyname, gethostbyaddr) or sendmsg. Hostile native code can go around it.
"""

import ipaddress
import sys

_installed = False

# The socket actions whose second argument is an address, and the words that name each action.
ADDRESS_EVENTS = {
    "socket.connect": "a connection to",
    "socket.sendto": "sending data to",
    "socket.bind": "opening a socket on",
}


def is_loopback_host(host: str) -> bool:
    """Return True only for localhost, an IPv4 address in 127.0.0.0/8, or ::1."""
    return host == "localhost" or is_loopback_ip(host)


def is_loopback_ip(host: str) -> bool:
    """Return True only for an IPv4 address in 127.0.0.0/8 or the IPv6 address ::1."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if address.version == 4:
        return address.is_loopback
    return address == ipaddress.IPv6Address("::1")


def is_loopback_address(address: object) -> bool:
    """Return True only for a socket address tuple that starts with a loopback IP address."""
    # Python resolves normal host names before a connect, so a name here is unusual and refused.
    return isinstance(address, tuple) and bool(address) and isinstance(address[0], str) and is_loopback_ip(address[0])


def is_local_lookup(host: object) -> bool:
    """Return True if a name lookup for this host stays on this computer."""
    if host is None:
        return True
    if isinstance(host, bytes):
        # A byte that is not ASCII becomes a character that no allowed host has.
        host = host.decode("ascii", errors="replace")
    return isinstance(host, str) and (host == "" or is_loopback_host(host))


def install() -> None:
    """Turn the guard on for this Python process. A second call does nothing."""
    global _installed
    if _installed:
        return
    sys.addaudithook(_check_event)
    _installed = True


def _check_event(event: str, args: tuple) -> None:
    # Python calls this for every audited event, so other events must return at once.
    if not event.startswith("socket."):
        return
    if event == "socket.getaddrinfo" and not is_local_lookup(args[0]):
        raise PermissionError(f"Korvin blocked a name lookup for {args[0]}. Only this computer is allowed.")
    if event in ADDRESS_EVENTS and not is_loopback_address(args[1]):
        raise PermissionError(f"Korvin blocked {ADDRESS_EVENTS[event]} {args[1]}. Only this computer is allowed.")
