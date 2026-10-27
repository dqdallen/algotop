import socket
import unittest
from unittest.mock import Mock, patch
import safe_transport as st

class SafeTransportTests(unittest.TestCase):
    def test_private_and_mixed_dns_rejected(self):
        for addresses in [['127.0.0.1'], ['8.8.8.8','169.254.169.254'],['::1'], ['10.0.0.1'], ['2002:7f00:1::'], ['::ffff:8.8.8.8']]:
            rows=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in addresses]
            with patch.object(st.urllib.request,'getproxies',return_value={}),patch.object(st.socket,'getaddrinfo',return_value=rows),patch.object(st,'PinnedHTTPSConnection') as conn:
                with self.assertRaisesRegex(ValueError,'nonpublic_destination'):st.direct_transport('https://example.com/a',{'example.com'})
                conn.assert_not_called()
    def test_proxy_refusal_and_allowlist(self):
        with patch.object(st.urllib.request,'getproxies',return_value={'https':'http://managed:80'}):
            with self.assertRaisesRegex(ValueError,'managed_proxy_present'):st.direct_transport('https://example.com/',{'example.com'})
        with patch.object(st.urllib.request,'getproxies',return_value={}):
            with self.assertRaisesRegex(ValueError,'host_not_allowed'):st.direct_transport('https://other.example/',{'example.com'})
    def test_pins_numeric_address_tls_host(self):
        raw=Mock();wrapped=Mock();context=Mock();context.wrap_socket.return_value=wrapped
        with patch.object(st.socket,'create_connection',return_value=raw) as dial,patch.object(st.ssl,'create_default_context',return_value=context):
            conn=st.PinnedHTTPSConnection('example.com','8.8.8.8',timeout=15);conn.connect()
            self.assertEqual(dial.call_args.args[0],('8.8.8.8',443))
            context.wrap_socket.assert_called_once_with(raw,server_hostname='example.com')
            self.assertIs(conn.sock,wrapped)
    def test_redirect_not_followed_and_safe_headers(self):
        rows=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
        with patch.object(st.urllib.request,'getproxies',return_value={}),patch.object(st.socket,'getaddrinfo',return_value=rows),patch.object(st,'PinnedHTTPSConnection') as factory:
            conn=factory.return_value;response=conn.getresponse.return_value
            response.status=302;response.getheader.return_value='text/plain';response.read.return_value=b''
            self.assertEqual(st.direct_transport('https://example.com/a?q=x',{'example.com'})[0],302)
            self.assertEqual(factory.call_count,1);self.assertEqual(factory.call_args.args,('example.com','8.8.8.8'))
            call=conn.request.call_args
            self.assertEqual(call.args,('GET','/a?q=x'))
            self.assertEqual(call.kwargs['headers']['Host'],'example.com')
            self.assertNotIn('Authorization',call.kwargs['headers']);conn.close.assert_called_once()
    def test_body_size_bound(self):
        rows=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
        with patch.object(st.urllib.request,'getproxies',return_value={}),patch.object(st.socket,'getaddrinfo',return_value=rows),patch.object(st,'PinnedHTTPSConnection') as factory:
            response=factory.return_value.getresponse.return_value;response.read.return_value=b'x'*(st.MAX_BYTES+1)
            with self.assertRaisesRegex(ValueError,'response_limit'):st.direct_transport('https://example.com/',{'example.com'})
            response.read.assert_called_once_with(st.MAX_BYTES+1)
    def test_credentials_and_ip_literals_rejected(self):
        with patch.object(st.urllib.request,'getproxies',return_value={}):
            for url in ['https://u:p@example.com/','https://127.0.0.1/','http://example.com/']:
                with self.assertRaises(ValueError):st.direct_transport(url,{'example.com'})
