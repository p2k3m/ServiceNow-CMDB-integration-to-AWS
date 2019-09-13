# Data object for the ELB RDS resource we want to hand over to SNOW
# Takes the AWS Config message and processes it
# Contains also the function to map the AWS Config processed object to a SNOW object
from .generic import SnowAwsGenericObject
from datetime import datetime


class SnowRDSObject(SnowAwsGenericObject):
    '''Inherits attributes from SnowAwsGenericObject, and adds RDS-specific attributes.'''

    def __init__(self, message):
        super().__init__(message)

        self.model_id = None
        self.version = None
        self.u_rds_name = None
        self.u_engine = None
        self.u_rds_engine_version = None
        self.u_rds_instance_status = None
        self.u_rds_instance_identifier = None
        self.u_rds_cluster_identifier = None
        self.u_rds_auto_minor_version_upgrade = None
        self.u_state = None
        self.u_instance_id = None

        self._set_values(message)

    def _get_snow_table(self):
        return 'u_imp_aws_rds_instance'

    def _set_values(self, message):
        '''Set the values'''
        super()._set_values(message)

        conf_item = message['configurationItem']

        self.asset_tag = conf_item['resourceId']
        self.u_arn = conf_item['ARN']
        self.name = conf_item['resourceName']
        self.u_rds_name = conf_item['resourceName']

        # mark the instance state correctly if the instance is deleted
        if self.change_type == 'DELETE':
            self.state = 'terminated'

        # This is set to none if change notification type is DELETE
        if conf_item['configuration'] is not None:
            rds_conf = conf_item['configuration']

            self.model_id = rds_conf['dBInstanceClass']
            self.u_engine = rds_conf['engine']
            self.version = rds_conf['engineVersion']
            self.u_state = rds_conf['dBInstanceStatus'],
            if 'dBInstanceIdentifier' in rds_conf:
                self.u_instance_id = rds_conf['dBInstanceIdentifier']
            self.u_rds_auto_minor_version_upgrade = rds_conf['autoMinorVersionUpgrade']
            self.u_availability_zone = conf_item['availabilityZone']
            # TODO: Carrie, there are a lot of differences, like in ec2 its "install_date", in RDS its "installed"
            self.installed = datetime.strptime(conf_item['resourceCreationTime'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d %H:%M:%S')

            # TODO: didn't find licenseModel in RDS output... at least not aurora
            #self.u_license_model=instance['LicenseModel']
