"""Explicit direct egress for dedicated runners without an existing managed proxy.

Caller must opt in and supply reviewed policy hostnames. Never use this transport
as a fallback after managed transport fails. TLS uses hostname verification while
the connection is pinned to one prevalidated numeric public destination address.
"""
import http.client
import ipaddress
import socket
import ssl
import urllib.parse
import urllib.request
from ingest import AGENT, MAX_BYTES, canonical


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, *, timeout=15):
        super().__init__(host,port=443,timeout=min(max(timeout,1),15),context=ssl.create_default_context())
        self.address=address

    def connect(self):
        # Numeric address: socket performs no new hostname resolution. No tunnel,
        # proxy, alternate endpoint, client credentials, or unverified TLS context.
        raw=socket.create_connection((self.address,443),self.timeout)
        try:
            self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def direct_transport(url,allowed_hosts):
    """Return (status, content_type, bounded bytes); never follow redirects.

    Existing proxy configuration wins even if NO_PROXY would bypass it. DNS must
    contain only globally routable unicast answers. No custom CA/no-verify knobs.
    Requires normal DNS availability on the explicitly opted-in runner.
    """
    proxies=urllib.request.getproxies()
    if any(str(key).lower() in {'http','https','all'} and value for key,value in proxies.items()):
        raise ValueError('managed_proxy_present')
    url=canonical(url);parts=urllib.parse.urlsplit(url);host=parts.hostname
    if host not in allowed_hosts:raise ValueError('host_not_allowed')
    try:
        answers=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM,proto=socket.IPPROTO_TCP)
        addresses=[]
        for family,kind,protocol,name,sockaddr in answers:
            if family not in {socket.AF_INET,socket.AF_INET6}:raise ValueError('nonpublic_destination')
            ip=ipaddress.ip_address(sockaddr[0])
            # is_global alone includes some special multicast ranges on some
            # Python versions. Explicit exclusions keep the policy conservative.
            if not ip.is_global or ip.is_multicast or ip.is_unspecified or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                raise ValueError('nonpublic_destination')
            if isinstance(ip,ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo):
                raise ValueError('nonpublic_destination')
            addresses.append(str(ip))
        if not addresses:raise ValueError('dns_empty')
    except ValueError:raise
    except Exception:raise ValueError('dns_failed') from None
    connection=PinnedHTTPSConnection(host,addresses[0],timeout=15)
    try:
        target=urllib.parse.urlunsplit(('','',parts.path or '/',parts.query,''))
        connection.request('GET',target,headers={'Host':host,'User-Agent':AGENT,'Accept':'application/json,application/xml,text/xml,application/rss+xml,application/atom+xml,text/html,text/plain','Accept-Encoding':'identity'})
        response=connection.getresponse()
        body=response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:raise ValueError('response_limit')
        return response.status,response.getheader('Content-Type',''),body
    finally:
        connection.close()
