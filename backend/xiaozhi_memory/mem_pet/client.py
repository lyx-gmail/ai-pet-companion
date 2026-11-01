"""Loopback-only client for the separately authenticated pet memory service."""
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler


class MemoryUnavailable(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PetMemoryClient:
    def __init__(self, endpoint, token, timeout=3):
        url = urlsplit(endpoint)
        if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost')
                or url.username or url.password or url.query or url.fragment
                or url.path not in ('', '/')):
            raise ValueError('LOOPBACK_ENDPOINT_REQUIRED')
        if not isinstance(token, str) or not token or any(c in token for c in '\r\n'):
            raise ValueError('TOKEN_REQUIRED')
        if not 0 < timeout <= 30:
            raise ValueError('TIMEOUT_INVALID')
        self.endpoint = endpoint.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def recall(self, query):
        if not isinstance(query, str) or not query.strip() or len(query.encode('utf-8')) > 2000:
            raise ValueError('QUERY_INVALID')
        context=self._post('recall',{'query':query})['context']
        if not isinstance(context,str): raise MemoryUnavailable('CONTEXT_INVALID')
        return context

    def request(self, operation, body):
        if operation not in ('remember','confirm','cancel','propose'):
            raise ValueError('MEMORY_OPERATION_INVALID')
        return self._post(operation,body,30 if operation=='remember' else self.timeout)

    def profile(self):
        request=Request(self.endpoint+'/api/profile',headers={'Authorization':'Bearer '+self.token})
        return self._send(request)

    def recall_snapshot(self, query):
        if not isinstance(query,str) or not query.strip() or len(query.encode('utf-8'))>2000:
            raise ValueError('QUERY_INVALID')
        result=self._post('recall',{'query':query})
        revision=result.get('profile',{}).get('revision') if isinstance(result.get('profile'),dict) else None
        if type(revision) is not int or not 0<=revision<=9007199254740991 or not isinstance(result.get('context'),str):
            raise MemoryUnavailable('MEMORY_SNAPSHOT_INVALID')
        return result

    def _post(self, operation, body, timeout=None):
        request = Request(self.endpoint + '/api/'+operation,
                          data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                          headers={'Authorization': 'Bearer ' + self.token,
                                   'Content-Type': 'application/json'}, method='POST')
        return self._send(request,timeout)

    def _send(self, request, timeout=None):
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('RESPONSE_TOO_LARGE')
            result=json.loads(raw)
            if not isinstance(result,dict) or 'error' in result:
                raise ValueError('MEMORY_RESPONSE_INVALID')
            return result
        except HTTPError as error:
            try:
                with error:
                    code=json.loads(error.read(4097)).get('error')
                if code in ('CONFLICT','BUSY','EXPIRED','NOT_FOUND'):
                    raise MemoryUnavailable(code) from None
            except (ValueError,AttributeError):
                pass
            raise MemoryUnavailable('MEMORY_UNAVAILABLE') from None
        except Exception:
            raise MemoryUnavailable('MEMORY_UNAVAILABLE') from None
