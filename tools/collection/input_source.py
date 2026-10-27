"""Bounded input text for extraction. No authorization is implied by an import.

Text and hashes are transient return values; callers must keep private inputs out
of logs/artifacts. Offsets refer to this returned text, not the original HTML.
"""
import hashlib
import os
import re
import time
from urllib.parse import urlsplit
from html.parser import HTMLParser
from html import escape

from ingest import MAX_BYTES, Pipeline, canonical, transport as managed_transport

MAX_TEXT_CHARS = 40_000


class InputSourceError(ValueError):
    """Constant safe-to-display failure code, never a remote error or body."""


class _VisibleText(HTMLParser):
    _skip = {'script', 'style', 'template', 'noscript', 'iframe', 'head', 'svg', 'nav', 'footer', 'aside', 'object', 'embed'}
    _void = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
    _blocks = {'p', 'div', 'li', 'ul', 'ol', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'tr', 'blockquote', 'pre', 'br', 'hr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tag_positions = {}
        self.parts = []
        self.safe_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = re.sub(r'\s+', '', attrs.get('style') or '').lower()
        hidden = (bool(self.stack and self.stack[-1][1]) or tag in self._skip
                  or 'hidden' in attrs or (attrs.get('aria-hidden') or '').lower() == 'true'
                  or 'display:none' in style or 'visibility:hidden' in style)
        if tag in self._blocks and not hidden:
            self.parts.append('\n')
            self.safe_parts.append('<'+tag+'>')
        if tag not in self._void:
            self.tag_positions.setdefault(tag, []).append(len(self.stack))
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        # Conservative on malformed markup: never reveal a still-hidden subtree.
        # Per-tag positions make unmatched closing tags O(1), not a reverse
        # scan of every open element. Each frame is pushed/popped at most once:
        # even adversarial malformed nesting has linear total stack work.
        positions = self.tag_positions.get(tag)
        if positions:
            index = positions[-1]
            while len(self.stack) > index:
                closed_tag, _ = self.stack.pop()
                closed_positions = self.tag_positions[closed_tag]
                closed_positions.pop()
                if not closed_positions:
                    del self.tag_positions[closed_tag]
        if tag in self._blocks and not (self.stack and self.stack[-1][1]):
            self.parts.append('\n')
            self.safe_parts.append('</'+tag+'>')

    def handle_data(self, data):
        if not self.stack or not self.stack[-1][1]:
            self.parts.append(data)
            self.safe_parts.append(escape(data))


def load_import(text, url, kind='text'):
    """Load explicit user-supplied text/HTML, without fetching any URL.

    The URL is attribution supplied by the user, not proof of origin, publication
    permission, or crawler authorization. Nothing is silently truncated.
    """
    if kind not in {'text', 'html'} or not isinstance(text, str):
        raise InputSourceError('invalid_input')
    try:
        source_url = canonical(url)
        size = len(text.encode('utf-8'))
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise InputSourceError('invalid_input') from None
    if size > MAX_BYTES:
        raise InputSourceError('input_too_large')
    parser_info = {'used_parser': 'plain_text', 'parser_version': None, 'parser_fallback_reason': None}
    if kind == 'html':
        parser = _VisibleText()
        parser.feed(text)
        parser.close()
        # Strip active/hidden subtrees and every attribute before the optional
        # parser sees HTML. No URL, script, entity declaration or external asset
        # is passed to the parser. extract() processes data; it never fetches.
        text = '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
        # Bound even text a readability parser might otherwise omit.
        if len(text) > MAX_TEXT_CHARS:
            raise InputSourceError('input_too_large')
        parser_info['used_parser'] = 'html_fallback'
        try:
            import trafilatura
        except ImportError:
            parser_info['parser_fallback_reason'] = 'dependency_unavailable'
        else:
            try:
                extracted = trafilatura.extract(
                    '<html><body>'+''.join(parser.safe_parts)+'</body></html>',
                    output_format='txt', include_comments=False,
                    include_links=False, include_images=False,
                    with_metadata=False)
                extracted = '\n'.join(line.strip() for line in (extracted or '').splitlines() if line.strip())
                if extracted:
                    text = extracted
                    parser_info.update(used_parser='trafilatura', parser_version=trafilatura.__version__)
                else:
                    parser_info['parser_fallback_reason'] = 'empty_result'
            except Exception:
                # Never expose parser exceptions containing private source text.
                parser_info['parser_fallback_reason'] = 'parser_error'
    if len(text) > MAX_TEXT_CHARS:
        raise InputSourceError('input_too_large')
    if not text.strip():
        raise InputSourceError('empty_input')
    return {'source_url': source_url, 'input_kind': 'user_supplied_'+kind,
            **parser_info, 'access_status': 'user_supplied_unverified',
            'text': text, 'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def fetch_source(url, policy, cache, transport=None, *, today=None, sleeper=time.sleep):
    """Fetch one policy-approved source using unchanged existing network gates.

    Requires a separately reviewed body_extraction_status='permitted' host
    rule in addition to the existing policy/date/path/robots checks. Existing
    metadata-discovery permission never authorizes body extraction.
    Captures the body in memory while Pipeline keeps only its metadata cache.
    A metadata cache hit cannot stand in for original text; it fails closed.
    Production requires ALGOTOP_TRUSTED_EGRESS=1 as an operator acknowledgement
    of the managed HTTPS proxy trust contract: the proxy must
    deny private/link-local destinations and enforce egress/DNS policy. This
    module does not pretend local DNS resolution pins a proxy-side connection.
    The injectable transport is only for offline tests, not an egress fallback.
    """
    try:
        url = canonical(url)
    except (ValueError, TypeError, AttributeError):
        raise InputSourceError('invalid_input') from None
    captured = {}
    http = transport or managed_transport

    def bounded_capture(target):
        code, content_type, body = http(target)
        if not isinstance(body, bytes) or len(body) > MAX_BYTES:
            raise ValueError('response_limit')
        if target == url:
            captured['body'] = body
            captured['content_type'] = content_type
        return code, content_type, body

    pipeline = Pipeline(cache, policy, transport=bounded_capture, today=today, sleeper=sleeper)
    if not pipeline.permitted(url):
        raise InputSourceError('policy_blocked')
    if policy.get(urlsplit(url).hostname, {}).get('body_extraction_status') != 'permitted':
        raise InputSourceError('body_policy_blocked')
    if transport is None and os.environ.get('ALGOTOP_TRUSTED_EGRESS') != '1':
        raise InputSourceError('trusted_egress_required')
    record = pipeline.fetch(url)
    status = record.get('status')
    if status == 'cached_unverified':
        raise InputSourceError('cached_body_unavailable')
    if status != 'fetched_unverified' or 'body' not in captured:
        safe_status = status if status in {'policy_blocked', 'host_paused', 'robots_unavailable', 'robots_blocked', 'unsupported_content'} or (isinstance(status, str) and re.fullmatch(r'http_\d{3}', status)) else 'fetch_error'
        raise InputSourceError(safe_status)
    kind = 'html' if 'html' in captured['content_type'].split(';')[0].lower() else 'text'
    result = load_import(captured['body'].decode('utf-8', 'replace'), url, kind)
    result['input_kind'] = 'policy_fetched_'+kind
    result['access_status'] = 'policy_fetched_unverified'
    return result
