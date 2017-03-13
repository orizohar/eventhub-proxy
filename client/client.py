from azure.servicebus import ServiceBusService
import argparse
import os
import datetime
import json
import hashlib
import random
import string

class SbClient():
    def __init__(self, namespace, keyname, keyval, eh_name):
        self._sbs = ServiceBusService(service_namespace=namespace, 
                        shared_access_key_name=keyname,
                        shared_access_key_value=keyval)
        self._eh_name = eh_name
    
    def send(self, msg_body):
        time_stamp = unicode(datetime.datetime.now())
        hash_object = hashlib.md5()
        hash_object.update(time_stamp)
        hash_object.update(msg_body)
        identifier = hash_object.hexdigest()
        msg = {'id' : identifier, 'timestamp' : time_stamp, 'msg' : msg_body }
        event_msg = json.dumps(msg)
        print('Sending {0}'.format(event_msg))
        self._sbs.send_event(self._eh_name, event_msg)

def main(namespace, keyname, keyval, eh_name):
    client = SbClient(namespace, keyname, keyval, eh_name)
    random_msg_body = ''.join(random.choice(string.lowercase) for i in range(16))
    client.send(random_msg_body)
    
if __name__ == '__main__':
    namespace = os.getenv('SB_NAMESPACE')
    keyname = os.getenv('SB_KEYNAME')
    keyval = os.getenv('SB_KEYVAL')
    eh_name = os.getenv('EH_NAME', 'ingest')
    if (not namespace) or (not keyname) or (not keyval):
        print ('ERROR: Missing env vars SB_NAMESPACE, SB_KEYNAME, SB_KEYVAL')
        print ('Exiting...')
        exit(1)
    main(namespace, keyname, keyval, eh_name)
