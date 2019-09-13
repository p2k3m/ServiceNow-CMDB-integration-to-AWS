# Generic data object with values that every AWS resource should define
# Contains also the function to map the AWS Config message to a SNOW object
import pprint
import requests
import sys
import logging
import json
from datetime import datetime


class SnowAwsGenericObject():
    '''Generic object for SNOW with values that every other AWS object should have'''
    def __init__(self, message):
        # Object related settings that should be used by every object
        self.install_date = None
        self.asset_tag = None
        self.name = None
        self.cost_center = None
        self.state = None
        self.u_region = None
        self.u_account_id = None
        self.u_used_for = None
        self.u_service_tag = None
        self.u_availability_zone = None
        self.u_group = None
        self.u_backup_group = None
        self.u_pod = None
        self.u_poc = None
        self.u_classification = None
        self.u_additional_tags = None
        self.u_expiration = None
        self.u_last_change_update = None
        self.u_last_change_snapshot = None
        self.u_last_change_delete = None
        self.u_last_change_create = None

        self._set_values(message)

    def _set_values(self, message):
        '''Standard values we expect all the resource types to need to use.  Resource-specific attributes will be listed in that particular resource type.'''
        if 'configurationItem' not in message:
            logging.fatal("if 'configurationItem' not in message: in generic.py")
            pprint.pprint(message)
            sys.exit(1)
        tags = message['configurationItem']['tags']
        if tags is not None:
            v_additional_tags = ''
            for tag in tags:
                # Two tag options, one via key & value naming, one without
                key = None
                value = None
                if 'key' in tag:
                    key = tag['key'].upper()
                    value = tag['value']
                else:
                    key = tag.upper()
                    value = tags[tag]

                if key == 'COSTCENTER':
                    self.cost_center = value
                elif key == 'NAME':
                    self.name = value
                elif key == 'ENVIRONMENT':
                    self.u_used_for = value
                    self.used_for = value
                elif key == 'SERVICE':
                    self.u_service_tag = value
                elif key == 'BACKUPGROUP':
                    self.u_backup_group = value
                elif key == 'GROUP':
                    self.u_group = value
                elif key == 'EXPIRATION':
                    self.u_expiration = value
                elif key == 'CLIENT':
                    self.u_client = value
                elif key == 'POD':
                    self.u_pod = value
                elif key == 'POC':
                    self.u_poc = value
                elif key == 'CLASSIFICATION':
                    self.u_classification = value
                else:
                    v_additional_tags += key + '=' + value + '; '
            if v_additional_tags:
                self.u_additional_tags = v_additional_tags.rstrip('; ')
        self.u_account_id = message['configurationItem']['awsAccountId']
        if 'configurationItemDiff' in message:
            self.change_type = message['configurationItemDiff']['changeType']
        else:
            self.change_type = 'snapshot'
        # There are some cases where there might not be a region. Like IAM...
        # didn't face it yet, but lets have it implemented
        # TODO: remove
        if 'awsRegion' not in message['configurationItem']:
            pprint.pprint(message)
            print("awsRegion not in message in generic.py")
            sys.exit(1)
        if message['configurationItem']['awsRegion']:
            self.u_region = message['configurationItem']['awsRegion']

        # Set all the time fields...
        capture_time = datetime.strptime(message['configurationItem']['configurationItemCaptureTime'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d %H:%M:%S')
        if self.change_type == 'snapshot':
            self.u_last_change_snapshot = capture_time
        elif self.change_type == 'UPDATE':
            self.u_last_change_update = capture_time
        elif self.change_type == 'DELETE':
            self.u_last_change_delete = capture_time
        elif self.change_type == 'CREATE':
            self.u_last_change_create = capture_time

        # resourceCreationTime doesn't exist in AWS::SSM::ManagedInstanceInventory
        if 'resourceCreationTime' in message['configurationItem'] and message['configurationItem']['resourceCreationTime'] is not None:
            self.install_date = datetime.strptime(message['configurationItem']['resourceCreationTime'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d %H:%M:%S')

    def submit_data_to_snow(self, data, args):
        '''Sends the object to SNOW'''
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Args only here to not accidently expose the credentials and to have
        # a much easyer and simple vars(self)
        snow_user = args['snow_user']
        snow_password = args['snow_password']
        snow_url = "https://{}/api/now/import/{}".format(args['snow_hostname'], self._get_snow_table())

        try:
            logging.debug("Submitting data to SNOW")
            response = requests.post(snow_url, auth=(snow_user, snow_password), headers=headers, data=json.dumps(data))
        except Exception as e:
            logging.fatal("Used requests.post(%s, ....)" % snow_url)
            logging.fatal("Failed to submit data to SNOW. %s" % e)
            logging.fatal("Data submitted:")
            pprint.pprint(data)
            sys.exit(1)

        if response.status_code != 201:
            logging.fatal("Used requests.post(%s, ....)" % snow_url)
            logging.fatal("Failed to submit data to SNOW. Response status code isn't 201.")
            logging.fatal("Status Code: %s, Response Headers: %s, Error Response: %s" % (response.status_code, response.headers, response.text))
            logging.fatal("User authentication errors could also mean 'permission denied'. SNOW is kinda buggy here")
            sys.exit(1)

    def add_to_snow(self, args):
        '''Add data to snow.
        We have two functions because SSM Inventory overwrites this block and
        we don't want to duplicate the function'''

        data = vars(self)
        self.submit_data_to_snow(data, args)

    def __str__(self):
        return str(vars(self))

    def __repr__(self):
        return pprint.pformat(vars(self))
