import base64
import hashlib
import hmac
import sys
import urllib
import time
import requests
import os
import random
import string
import datetime
import json

def pretty_print(req):
    """ Prints a Request object for debug/log purposes.
    req should be a prepared Request object
    """
    print('{}\n{}\n{}\n\n{}\n{}\n'.format(
        '-----------Request-----------',
        req.method + ' ' + req.url,
        '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
        '-----------------------------',
    ))

def generate_message(body=None):
    """ Generate a JSON message in the form:
    {
        "msg" : <16 Random characters>,
        "timestamp" : <String with current time>
        "id" : <Hash of above fields>
    }
    """
    if not body:
        body = ''.join(random.choice(string.lowercase) for i in range(16))
    time_stamp = unicode(datetime.datetime.now())
    hash_object = hashlib.md5()
    hash_object.update(time_stamp)
    hash_object.update(body)
    identifier = hash_object.hexdigest()
    msg = {'id' : identifier, 'timestamp' : time_stamp, 'msg' : body }
    event_msg = json.dumps(msg)
    return event_msg

AUTH_EXPIRE_SEC = 300

class ProxyClient():
    """ This class represents a client for sending messages to evenhub via some proxy """

    def __init__(self, proxy, namespace, eh_name, keyname, keyval, cert_path=None):
        """ Initialize the class. Arguments:
            proxy - the DNS or IP address of the proxy
            namespace - the event hub namespace
            eh_name - the event hub  namespace
            keyname - the name of the key to be used for SharedAccessSignature
            keyvalue - the key to be used for SharedAccessSignature
        """
        self.proxy = proxy
        self.namespace = namespace
        self.eh_name = eh_name
        self.keyname = keyname
        self.keyval = keyval
        self.cert_verify = cert_path or True
        
    def generate_auth(self):
        """ Generate the Authorization header to be sent to event hub"""
        uri = '{0}.servicebus.windows.net'.format(self.namespace.lower())
        expiry = str(int(round(time.time() + AUTH_EXPIRE_SEC)))
        to_sign = uri + '\n' + expiry
        signed_hmac_sha256 = hmac.HMAC(self.keyval, to_sign, hashlib.sha256)
        digest = signed_hmac_sha256.digest()
        encoded = base64.b64encode(digest)
        encoded_digest =  encoded.decode('utf-8')
        signature = urllib.quote(encoded_digest, '')
        auth_format = 'SharedAccessSignature sig={0}&se={1}&skn={2}&sr={3}'
        auth = auth_format.format(signature, expiry, self.keyname, uri)
        return auth

    def send(self, msg):
        """ Send the HTTP POST request to the proxy. 
            Note that the HTTP request is sent to the proxy but the Host header and SAS uses the event hub namespace FQDN
        """
        url = 'https://{0}'.format(self.proxy) + '/{0}/messages'.format(self.eh_name)
        headers = {
            'Authorization' : self.generate_auth(),
            'Content-Type': 'application/atom+xml;type=entry;charset=utf-8 ',
            'Host' : '{0}.servicebus.windows.net'.format(self.namespace)
        }
        arguments = {
            'api-version' : '2014-01', 
            'timeout' : '60'
        }
        req = requests.Request('POST', url=url, params=arguments, headers=headers, data=msg)
        prepared = req.prepare()
        pretty_print(prepared)
        s = requests.Session()
        r = s.send(prepared, verify=self.cert_verify)
        return r.status_code

def main():
    proxy = os.getenv('EH_PROXY_DNS')
    namespace = os.getenv('SB_NAMESPACE')
    eh_name = os.getenv('EH_NAME')
    keyname = os.getenv('SB_KEYNAME')
    keyval = os.getenv('SB_KEYVAL')
    cert_path = os.getenv('EH_PROXY_CERT_PATH')

    if (not proxy) or (not namespace) or (not eh_name) or (not keyname) or (not keyval): 
        print 'Missing env vars. Please make sure the following are defined:'
        print '\tEH_PROXY_DNS : IP or DNS of proxy.'
        print '\tSB_NAMESPACE : Service bus namespace for event hub'
        print '\tEH_NAME : Event hub name'
        print '\tSB_KEYNAME : SAS access key name'
        print '\tSB_KEYVAL : SAS access key value'
        exit(1)

    pc = ProxyClient(proxy, namespace, eh_name, keyname, keyval, cert_path)
    msg = generate_message()
    ret = pc.send(msg)
    print 'Send status: {0}'.format(ret)

if __name__ == '__main__':
    main()