from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from fastapi import Request


IPAddress = IPv4Address | IPv6Address


class TrustedClientAddressResolver:
    """Resolve a client address without trusting headers from direct clients."""

    def __init__(self, trusted_proxy_networks: tuple[str, ...]) -> None:
        self._trusted_proxy_networks = tuple(
            ip_network(network, strict=False) for network in trusted_proxy_networks
        )

    def resolve(self, request: Request) -> str:
        """Return the first untrusted hop walking away from the application."""
        if request.client is None:
            raise ValueError("Client address is unavailable")

        current = ip_address(request.client.host)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for is None:
            return current.compressed

        for candidate in reversed(forwarded_for.split(",")):
            if not self._is_trusted_proxy(current):
                break
            current = ip_address(candidate.strip())

        return current.compressed

    def _is_trusted_proxy(self, address: IPAddress) -> bool:
        return any(address in network for network in self._trusted_proxy_networks)
