# Data object for the EC2 AWS resource we want to hand over to SNOW
# Takes the AWS Config message and processes it
# Contains also the function to map the AWS Config processed object to a SNOW object
from .generic import SnowAwsGenericObject


class SnowEc2Object(SnowAwsGenericObject):
    '''Inherits attributes from SnowAwsGenericObject, and adds EC2-specific attributes.'''
    def __init__(self, message):
        super().__init__(message)

        self.model_id = None
        self.u_ami = None
        self.u_instance_id = None
        self.u_platform = None
        self.u_monitoring_state = None
        self.u_private_ip_address = None
        self.u_public_ip_address = None
        self.u_tenancy = None
        self.u_host_id = None
        self.u_pricing_type = None
        self.u_cpu_threads_total_count = None
        self.u_cpu_threads_per_core = None
        self.u_cpu_core_count = None
        self.u_vpc_id = None
        self.u_termination_stopped_reason = None
        self.u_subnet_id = None

        self._set_values(message)

    def _get_snow_table(self):
        return 'u_imp_cmdb_ci_ec2_instance'

    def _set_values(self, message):
        '''Set the values'''
        super()._set_values(message)

        conf_item = message['configurationItem']

        self.asset_tag = conf_item['resourceId']
        self.u_instance_id = conf_item['resourceId']

        # mark the instance state correctly if the instance is deleted
        if self.change_type == 'DELETE':
            self.state = 'terminated'

        # This is set to none if change notification type is DELETE
        if conf_item['configuration'] is not None:
            ec2_conf = conf_item['configuration']

            self.u_availability_zone = conf_item['availabilityZone']
            self.u_ami = ec2_conf['imageId']
            self.model_id = ec2_conf['instanceType']
            self.state = ec2_conf['state']['name']
            self.u_tenancy = ec2_conf['placement']['tenancy']
            self.u_monitoring_state = ec2_conf['monitoring']['state']
            self.u_subnet_id = ec2_conf['subnetId']
            self.u_vpc_id = ec2_conf['vpcId']
            self.u_cpu_threads_per_core = ec2_conf['cpuOptions']['threadsPerCore']
            self.u_cpu_core_count = ec2_conf['cpuOptions']['coreCount']
            self.u_cpu_threads_total_count = self.u_cpu_threads_per_core * self.u_cpu_threads_per_core

            state_reason = None
            if 'stateReason' in ec2_conf:
                state_reason = ec2_conf['stateReason']
            self.u_termination_stopped_reason = 'StateReason: {}; StateTransitionReason: {}'.format(state_reason, ec2_conf['stateTransitionReason'])

            if 'spotInstanceRequestId' in ec2_conf and ec2_conf['spotInstanceRequestId']is not None:
                self.u_pricing_type = 'Spot Instance'
            else:
                self.u_pricing_type = 'On-Demand'
            if 'hostId' in ec2_conf['placement']:
                self.u_host_id = ec2_conf['placement']['hostId']
            if 'platform' in ec2_conf:
                self.u_platform = ec2_conf['platform']

            public_ips = set()
            if 'publicIpAddress' in ec2_conf and ec2_conf['publicIpAddress'] is not None:
                public_ips.add(ec2_conf['publicIpAddress'])
            private_ips = set([ec2_conf['privateIpAddress']])
            # There is an easy way above... and then there is the correct way to get all IP's
            for interface in ec2_conf['networkInterfaces']:
                # https://docs.aws.amazon.com/vpc/latest/userguide/VPC_ElasticNetworkInterfaces.html
                # TODO: This might not cover: one Elastic IP address per private IPv4 address
                #       Needs to be tested
                if 'association' in interface and interface['association'] is not None:
                    public_ips.add(interface['association']['publicIp'])
                for priv_ip in interface['privateIpAddresses']:
                    private_ips.add(priv_ip['privateIpAddress'])

            self.u_public_ip_address = ",".join(public_ips)
            self.u_private_ip_address = ",".join(private_ips)
