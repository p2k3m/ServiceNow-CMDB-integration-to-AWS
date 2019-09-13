# Data object for the SSM AWS resource we want to hand over to SNOW
# Takes the AWS Config message and processes it
# Contains also the function to map the AWS Config processed object to a SNOW object
from .generic import SnowAwsGenericObject
import pprint
import logging
import sys
import copy


class SnowSSMInventoryObject(SnowAwsGenericObject):
    '''Inherits attributes from SnowAwsGenericObject, and adds SSM-specific attributes.'''
    def __init__(self, message):
        super().__init__(message)

        self.package_changes = None
        self.all_packages = None
        self.u_version = None
        self.u_package = None
        self.id_type = None

        self._set_values(message)

    def _get_snow_table(self):
        return 'u_imp_aws_ec2_software_instance'

    def _set_values(self, message):
        '''Set the values'''
        super()._set_values(message)

        conf_item = message['configurationItem']

        self.asset_tag = conf_item['resourceId']
        self.id_type = conf_item['resourceId']
        self.package_changes = []
        self.all_packages = []

        # This is set to none if change notification type is DELETE. But let's
        # make sure we catch here every case... SSM Inventory seems to be
        # a bit different as the other resources. In the end this block is
        # just error checking
        if 'configuration' not in conf_item:
            # TODO: maybe replace some or only check for
            #       if conf_item['configurationItemStatus'] != 'ResourceDeleted'
            if 'configurationItemDiff' not in message:
                pprint.pprint(message)
                logging.fatal("Something is wrong. configuration not in conf_item & also no configurationItemDiff")
                sys.exit(1)
            if message['configurationItemDiff']['changeType'] != 'DELETE':
                pprint.pprint(message)
                logging.fatal("Something is wrong. configuration not in conf_item & changeType != DELETE")
                sys.exit(1)

        # This seems to be only hit if its a new instance.... they don't have
        # all the details, like no ssm_inventory_conf['AWS:Application']
        # bellow
        if conf_item['configurationItemStatus'] == 'ResourceDiscovered':
            logging.debug("New instance. It has only AWS::InstanceInformation' and no AWS:Application. Skipping configuration change check.")
            return

        # Finally we can check what has changed
        if 'configuration' in conf_item and conf_item['configuration'] is not None and 'AWS:Application' in conf_item['configuration']:
            ssm_inventory_conf = conf_item['configuration']

            # We ignore message['configuration']['AWS:AWSComponent'] since these
            # packages seem to be included in the 'AWS::Application' dictionary
            # We also ignore AWS:InstanceInformation & AWS:Network since we should
            # get this information in more verbose form from the EC2 snapshot & change
            # update
            packages = ssm_inventory_conf['AWS:Application']['Content']
            for package_name in packages:
                # Package name can contain multiple version. This is rare but
                # possible, e.g. with the kernel package
                if isinstance(packages[package_name], list):
                    for package_version in packages[package_name]:
                        self.all_packages.append(package_version)
                    continue

                # No good reason to make the dict an array, probably easier to process
                # later... and this allows us to modify exactly what we want to add
                # later without checking again how to iterate through it.
                # Stupid, I know, but code is already written...
                type(packages[package_name])
                self.all_packages.append(packages[package_name])

        # Changes to packages... with SoftwareInventory we handle changes differently
        # and need to process them
        if 'configurationItemDiff' in message:
            changes_raw = message['configurationItemDiff']['changedProperties']

            for changed_property in changes_raw:
                change_type = changes_raw[changed_property]['changeType']

                if change_type not in ['CREATE', 'DELETE', 'UPDATE']:
                    logging.fatal("Unknown SSM Inventory change type %s for %s" % (change_type, changed_property))
                    pprint.pprint(changes_raw[changed_property])
                    sys.exit(1)

                if change_type == 'UPDATE':
                    # The update is a little bit effed up. You can end up with various # changes that are unimportant, like install time or PackageId
                    # (where the packageId doesn't reflect the installed version itself)

                    # We ignore all _potential_ non-package changes (not tested)
                    if not changed_property.startswith('Configuration.AWS:Application.Content.'):
                        logging.debug("Skipping %s since its not a regular application" % changed_property)
                        continue

                self.package_changes.append(changes_raw[changed_property])

    def add_to_snow(self, args):
        '''Add data to snow.'''

        # Get the core structure without the data we need to itterate through
        data = copy.deepcopy(vars(self))
        del data['package_changes']
        del data['all_packages']

        # Two cases:
        # 1. snapshots & create: we submit all packages we found, in case we missed something
        # 2. updates: we only submit the changes, even though we have the full
        #    list. This saves a lot of resources
        # 3. We ignore DELETES since the entire instance gets marked as terminated
        #    DELETES here is not the changes of the package itself which has its own change_type
        if data['change_type'] in ['snapshot', 'CREATE']:
            for package in self.all_packages:
                data['u_package'] = package['Name']

                if 'Release' in package:
                    data['u_version'] = "{}-{}".format(package['Version'], package['Release'])
                else:
                    data['u_version'] = package['Version']

                #self.snow_submission(self, data, args)

        elif data['change_type'] == 'UPDATE':
            for package_change in self.package_changes:
                if package_change['changeType'] == 'CREATE':
                    package = package_change['updatedValue']
                    data['change_type'] == package_change['changeType']
                elif package_change['changeType'] == 'DELETE':
                    package = package_change['previousValue']
                    data['change_type'] == package_change['changeType']
                else:
                    print("TODO: not implemented/seen change %s yet" % package_change['changeType'])
                    pprint.pprint(package_change)
                    print("EXITING SCRIPT")
                    sys.exit(1)

                data['u_package'] = package['Name']
                if package_change['changeType'] == 'DELETE':
                    # Deleted packages are highlighted and processed with a prepended "-"
                    data['u_package'] = "-{}".format(data['u_package'])

                if 'Release' in package:
                    data['u_version'] = "{}-{}".format(package['Version'], package['Release'])
                else:
                    data['u_version'] = package['Version']

                #self.snow_submission(self, data, args)
