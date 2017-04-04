import base64
import hashlib
import hmac
import sys
from urllib import quote as url_quote
import time
import requests
import os
import random
import string
import datetime
import json

SAS_EXPIRE_SEC = 300

def generateSAS(namespace, eventhub_name, keyname, keyval):
    uri = '{0}.servicebus.windows.net'.format(namespace.lower())
    expiry = str(int(round(time.time() + SAS_EXPIRE_SEC)))
    to_sign = uri + '\n' + expiry
    signed_hmac_sha256 = hmac.HMAC(keyval, to_sign, hashlib.sha256)
    digest = signed_hmac_sha256.digest()
    encoded = base64.b64encode(digest)
    encoded_digest =  encoded.decode('utf-8')
    signature = url_quote(encoded_digest, '')
    auth_format = 'SharedAccessSignature sig={0}&se={1}&skn={2}&sr={3}'
    auth = auth_format.format(signature, expiry, keyname, uri)
    return auth

def pretty_print_POST(req):
    """
    At this point it is completely built and ready
    to be fired; it is "prepared".

    However pay attention at the formatting used in 
    this function because it is programmed to be pretty 
    printed and may differ from the actual request.
    """
    print('{}\n{}\n{}\n\n{}'.format(
        '-----------START-----------',
        req.method + ' ' + req.url,
        '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
    ))

def generateMessage(body=None):
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

def send(dest, namespace, eventhub_name, keyname, keyval, msg, cert_path=None):
    url = 'https://{0}'.format(dest)
    headers = {
        'Authorization' : generateSAS(namespace, eventhub_name, keyname, keyval),
        'Content-Type': 'application/atom+xml;type=entry;charset=utf-8 ',
        'Host' : '{0}.servicebus.windows.net'.format(namespace)
    }

    arguments = {
        'api-version' : '2014-01', 
        'timeout' : '60'
    }

    req = requests.Request('POST', url=url, params=arguments, headers=headers, data=msg)
    prepared = req.prepare()
    pretty_print_POST(prepared)

    s = requests.Session()

    # If no certificate path is given just set verify to True for certificate verification against installed CA
    cert_verify = cert_path or True
    r = s.send(prepared, verify=cert_verify)

    print r.status_code
    print r.text

if __name__ == '__main__':
    proxy = os.getenv('EH_PROXY_DNS')
    namespace = os.getenv('SB_NAMESPACE')
    eventhub_name = os.getenv('EH_NAME')
    keyname = os.getenv('SB_KEYNAME')
    keyval = os.getenv('SB_KEYVAL')
    cert_path = 'proxy\cert\cert.crt'

    msg = generateMessage()

    proxy += '/{0}/messages'.format(eventhub_name)

    send(proxy, namespace, eventhub_name, keyname, keyval, msg, cert_path)
