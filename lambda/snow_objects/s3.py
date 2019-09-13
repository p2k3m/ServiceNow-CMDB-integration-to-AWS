# Data object for the ELB S3 resource we want to hand over to SNOW
# Takes the AWS Config message and processes it
# Contains also the function to map the AWS Config processed object to a SNOW object
from .generic import SnowAwsGenericObject
import json


class SnowS3Object(SnowAwsGenericObject):
    '''Inherits attributes from SnowAwsGenericObject, and adds S3-specific attributes.'''

    def __init__(self, message):
        super().__init__(message)

        self.u_bucket_versioning = None
        self.u_bucket_logging_destination_bucket = None
        self.u_bucket_acl_allusers = None
        self.u_bucket_lifecycle = None

        self._set_values(message)

    def _get_snow_table(self):
        # TODO
        return 'TODO'

    def _set_values(self, message):
        '''Set the values'''
        super()._set_values(message)

        conf_item = message['configurationItem']

        self.asset_tag = conf_item['ARN']
        self.u_arn = conf_item['ARN']
        self.name = conf_item['resourceName']
        self.u_bucket_name = conf_item['resourceName']

        # This is set to none if change notification type is DELETE
        if conf_item['configuration'] is not None:
            s3_conf = conf_item['supplementaryConfiguration']
            self.u_bucket_versioning = s3_conf['BucketVersioningConfiguration']['status']
            if len(s3_conf['BucketLoggingConfiguration']) > 0:
                self.u_bucket_logging_destination_bucket = s3_conf['BucketLoggingConfiguration']['destinationBucketName']

            acl = json.loads(s3_conf['AccessControlList'])
            for grant in acl['grantList']:
                if grant['grantee'] == 'AllUsers':
                    self.u_bucket_acl_allusers = grant['permission']

            if 'BucketLifecycleConfiguration' in s3_conf:
                if len(s3_conf['BucketLifecycleConfiguration']['rules']) > 0:
                    self.u_bucket_lifecycle = True
