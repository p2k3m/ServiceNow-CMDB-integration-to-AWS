# Data object for the ELB AWS resource we want to hand over to SNOW
# Takes the AWS Config message and processes it
# Contains also the function to map the AWS Config processed object to a SNOW object
from .generic import SnowAwsGenericObject
from datetime import datetime
import pprint


class SnowElbObject(SnowAwsGenericObject):
    '''Inherits attributes from SnowAwsGenericObject, and adds ELB-specific attributes.'''

    def __init__(self, message):
        super().__init__(message)

        self.u_elb_scheme = None  # Elb scheme: public or private
        self.u_elb_type = None
        self.u_subnet_ids = None
        self.u_vpc_id = None
        self.u_cross_zone_enabled = None
        self.u_deletion_protection = None
        self.u_public_elb = None
        self.u_private_elb = None
        self.u_arn = None
        self.u_state = None

        self._set_values(message)

    def _get_snow_table(self):
        return 'u_imp_cmdb_ci_aws_elastic_load_balancer'

    def _set_values(self, message):
        '''Set the values'''
        super()._set_values(message)

        conf_item = message['configurationItem']

        self.asset_tag = conf_item['ARN']
        self.u_arn = conf_item['ARN']
        self.name = conf_item['resourceName']

        # This is set to none if change notification type is DELETE
        if conf_item['configuration'] is not None:
            elb_conf = message['configurationItem']['configuration']

            self.u_elb_scheme = elb_conf['scheme']

            if conf_item['resourceType'] == 'AWS::ElasticLoadBalancing::LoadBalancer':
                self.u_vpc_id = elb_conf['vpcid']
                self.u_elb_type = 'classic'
                self.u_availability_zone = ",".join(elb_conf['availabilityZones'])
                self.u_subnet_ids = ",".join(elb_conf['subnets'])
            elif conf_item['resourceType'] == 'AWS::ElasticLoadBalancingV2::LoadBalancer':
                self.state = elb_conf['state']['code']
                self.u_vpc_id = elb_conf['vpcId']
                self.u_elb_type = elb_conf['type']

                azs = [az['zoneName'] for az in elb_conf['availabilityZones']]
                self.u_availability_zone = ",".join(azs)

                subnets = [az['subnetId'] for az in elb_conf['availabilityZones']]
                self.u_subnet_ids = ",".join(subnets)

                elb_attr = conf_item['supplementaryConfiguration']['LoadBalancerAttributes']
                for attr in elb_attr:
                    if attr['key'] == 'load_balancing.cross_zone.enabled':
                        self.u_cross_zone_enabled = attr['value']
                    elif attr['key'] == 'deletion_protection.enabled':
                        self.u_deletion_protection = attr['value']

    def __str__(self):
        return str(vars(self))

    def __repr__(self):
        return pprint.pformat(vars(self))
