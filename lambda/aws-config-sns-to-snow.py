#!/usr/bin/env python3

# This code is used to cleanup data from AWS Config SNS topics, filter them
# for what we need and to change the datastructure so we can easier push it
# to SNOW
import argparse
import os
import os.path
import sys

root = os.environ["LAMBDA_TASK_ROOT"]
sys.path.insert(0, root)
import boto3
from botocore.exceptions import ClientError, ParamValidationError
import logging
import json
import pprint
import zlib

# make sure lambda finds the libraries
if 'LAMBDA_TASK_ROOT' in os.environ:
    CWD = os.path.dirname(os.path.realpath(__file__))
    sys.path.insert(0, os.path.join(CWD, "lib"))

# For AWS Config to SNOW object conversation
#  These require the requests library, hence its after the CWD config
from snow_objects.ec2 import SnowEc2Object  # noqa: E402
from snow_objects.elb import SnowElbObject  # noqa: E402
from snow_objects.s3 import SnowS3Object  # noqa: E402
from snow_objects.rds import SnowRDSObject  # noqa: E402
from snow_objects.ssm_inventory import SnowSSMInventoryObject  # noqa: E402


# List of resources we accept. We skip all other ones
ACCEPT_RESOURCES = [
    'AWS::EC2::Instance',
    'AWS::ElasticLoadBalancingV2::LoadBalancer',
    'AWS::ElasticLoadBalancing::LoadBalancer',
    'AWS::S3::Bucket',
    'AWS::SSM::ManagedInstanceInventory'
]

# ConfigurationHistoryDeliveryCompleted is just a bundle of
# ConfigurationItemChangeNotification which we process separately.
SKIP_MESSAGE_TYPES = [
    'ComplianceChangeNotification',
    'ConfigRulesEvaluationStarted',
    'ConfigurationHistoryDeliveryCompleted',
    'ConfigurationSnapshotDeliveryStarted'
]


def get_file_from_s3(bucket, key):
    '''Returns a key/file from S3 as object'''
    logging.debug("Function start")
    s3 = boto3.client('s3')
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except Exception as e:
        logging.fatal("Failed to download file from s3://%s/%s: %s" % (bucket, key, e))
        sys.exit(1)

    return obj['Body'].read()


def gunzip_object(obj):
    '''Takes object and gunzips it'''
    return zlib.decompress(obj, 16 + zlib.MAX_WBITS)


def get_file_from_s3_and_return_as_gunzip_json(bucket, key):
    '''Downloads the file from S3 and return it as gunziped json'''
    logging.debug("Function start")
    obj = get_file_from_s3(bucket, key)
    if key.endswith('.gz'):
        obj = gunzip_object(obj)
    if key.endswith('.json.gz'):
        message = json.loads(obj)
    else:
        logging.fatal("File in S3 didn't end in .json.gz: %s" % key)
        sys.exit(1)

    return message


def config_change_notification(message, args):
    '''Process ConfigurationItemChangeNotification & "adjusted" ConfigurationSnapshotDeliveryCompleted messages'''
    logging.debug("Function start")
    resource_type = message['configurationItem']['resourceType']

    # Resources to skip right away
    if resource_type not in ACCEPT_RESOURCES:
        logging.debug("Skipping %s" % resource_type)
        return

    if resource_type == 'AWS::EC2::Instance':
        snowObject = SnowEc2Object(message)
        snowObject.add_to_snow(args)
    elif resource_type == 'AWS::ElasticLoadBalancingV2::LoadBalancer':
        snowObject = SnowElbObject(message)
        #snowObject.add_to_snow(args)
    elif resource_type == 'AWS::ElasticLoadBalancing::LoadBalancer':
        snowObject = SnowElbObject(message)
        #snowObject.add_to_snow(args)
    elif resource_type == 'AWS::S3::Bucket':
        snowObject = SnowS3Object(message)
    elif resource_type == 'AWS::SSM::ManagedInstanceInventory':
        snowObject = SnowSSMInventoryObject(message)
        #snowObject.add_to_snow(args)
    elif resource_type == 'AWS::RDS::DBInstance':
        snowObject = SnowRDSObject(message)
    else:
        logging.warning("NEW ConfigurationItemChangeNotification kind: %s" % resource_type)
        return


def process_single_message(message, args):
    '''Processes a single message'''
    if 'messageType' not in message:
        logging.fatal("Unknown and unsupported message that doesn't contain messageType")
        pprint.pprint(message)
        sys.exit(1)

    message_type = message['messageType']
    logging.info("Processing %s" % message_type)

    # Skip messages we don't want based on the message type
    if message_type in SKIP_MESSAGE_TYPES:
        logging.debug("Skipping message type %s" % message_type)
        return

    # All notification kinds see
    # https://docs.aws.amazon.com/config/latest/developerguide/notifications-for-AWS-Config.html
    if message_type == 'ConfigurationItemChangeNotification':
        config_change_notification(message, args)

    elif message_type == 'OversizedConfigurationItemChangeNotification':
        # Skipping messages we don't care about. Saves a S3 download step
        if 'configurationItemSummary' in message and 'resourceType' in message['configurationItemSummary']:
            s3_resource_type = message['configurationItemSummary']['resourceType']
            if s3_resource_type not in ACCEPT_RESOURCES:
                logging.debug("Skipping in S3 hidden resource type %s" % s3_resource_type)
                return

        # Checking for S3 error
        if message['s3DeliverySummary']['errorCode'] is not None or message['s3DeliverySummary']['errorMessage'] is not None:
            logging.fatal("S3 delivery failed: %s - %s" % (message['s3DeliverySummary']['errorCode'], message['s3DeliverySummary']['errorMessage']))
            sys.exit(1)

        # Download & process
        bucket, key = message['s3DeliverySummary']['s3BucketLocation'].split("/", 1)
        s3_message = get_file_from_s3_and_return_as_gunzip_json(bucket, key)
        logging.debug("Reprocessing message we retrieved from S3")
        process_single_message(s3_message, args)

    elif message_type == 'ConfigurationSnapshotDeliveryCompleted':
        s3_message = get_file_from_s3_and_return_as_gunzip_json(message['s3Bucket'], message['s3ObjectKey'])

        for item in s3_message['configurationItems']:
            # Simulate a change_message so we only need one function to
            # process the data
            simulated_change_message = {
                'configurationItem': item,
            }
            # TODO: add to SQS to reduce runtime.
            config_change_notification(simulated_change_message, args)
    else:
        logging.warning("NEW resource messageType: %s" % message_type)
        return

    # TODO:
    # "messageType": "OversizedConfigurationItemChangeDeliveryFailed",


#
# Lambda specific function
#
def lambda_handler_sqs(event, context):
    args = lambda_arguments()
    _logger_config(args)

    records = event.get("Records", [])

    for record in records:
        try:
            core_message = json.loads(record['body'])
        except Exception as e:
            logging.fatal("SQS message doesn't seem to be a valid json. Error: %s, message: %s" % (e, record['body']))
            continue

        try:
            message = json.loads(core_message['Message'])
        except Exception as e:
            logging.fatal("SQS extracted message doesn't seem to contain 'Message' or isn't a valid json. Error %s: %s, message: %s" % (e, core_message))
            continue

        process_single_message(message, args)


#
# Old lambda event handler for sns input, no longer used after we moved to SQS
#
def lambda_handler_sns(event, context):
    args = lambda_arguments()
    _logger_config(args)

    if not (event and event['Records']):
        logging.fatal('Lambda needs to be invoked from an SNS topic: %s' % str(event))
        return

    # There should never be more as one record, but lets itterate in case AWS
    # ever decides that they want to break that...
    for record in event['Records']:
        if not record['Sns']:
            logging.fatal('Lambda input message is missing the SNS section: %s' % str(event))
            continue

        if not record['Sns']['Message']:
            logging.fatal('Lambda input message is missing the Message section: %s' % str(event))
            continue

        try:
            message = json.loads(record['Sns']['Message'])
        except Exception as e:
            logging.fatal("SNS message doesn't seem to be a valid json. Error: %s, message: %s" % (e, record['Sns']['Message']))
            continue

        process_single_message(message, args)



def get_secret_prod():
    #secret = []
    secret_name = "snow-integration"
    endpoint_url = "https://secretsmanager.us-east-1.amazonaws.com"
    region_name = "us-east-1"
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
        #endpoint_url=endpoint_url
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypted secret using the associated KMS CMK
        # Depending on whether the secret was a string or binary, one of these fields will be populated
        logging.fatal("Eric Hello")
        if 'SecretString' in get_secret_value_response:
            secret = json.loads(get_secret_value_response['SecretString'])
        else:
            secret = base64.b64decode(get_secret_value_response['SecretBinary'])
        
    #Data is returned as a JSON string. used json.loads to parse out the credentials and hostname for the DB.
    #logging.info("secret is ==>> "+secret[0])
    #logging.info("get_secret_value_response is ==>" + get_secret_value_response['SecretString'][0])
    
    snow_username = secret['snow_user']
    snow_password = secret['snow_password']
    snow_hostname = secret['snow_hostname']
    


   # data = json.loads(secret[0])
    #logging.info("data is ==> "+data)
    #snow_username = data['snow_username']
    #snow_password = data['snow_password']
    #snow_hostname = data['snow_hostname']
    
    
    
    return snow_username, snow_password, snow_hostname

#
# Functions related to running it from a dev machine and not via lambda
#

#snow_username, snow_password, snow_hostname = get_secret_prod()
def lambda_arguments():
    snow_username,snow_password,snow_hostname = get_secret_prod()
    return {
        
        'snow_secret': os.environ['SNOW_SECRET'],
        'snow_hostname': snow_hostname,
        'snow_user': snow_username,
        'snow_password': snow_password
#        'snow_hostname': os.environ['SNOW_HOSTNAME'],
#        'snow_user': os.environ['SNOW_USER'],
#        'snow_password': os.environ['SNOW_PASSWORD'],
#        'debug': False
    }
def parse_arguments():
    parser = argparse.ArgumentParser(description='Get minimum information required')
    parser.add_argument('--debug', '-d', dest='debug', action='store_true', required=False, help='Enable debugging output')
    parser.add_argument('--source-sqs-name', '-s', dest='source_sqs_name', default='', required=True, help='SQS queue name to take the data from')
    parser.add_argument('--region-sqs', '-r', dest='aws_region_sqs', default='', required=True, help='AWS Region of the SQS queue')
    parser.add_argument('--snow-hostname', '-n', dest='snow_hostname', default='', required=True, help='SNOW hostname, HOSTNAME in https://HOSTNAME/, no https etc.')
    parser.add_argument('--snow-user', '-u', dest='snow_user', default='', required=True, help='SNOW API User')
    parser.add_argument('--snow-password', '-p', dest='snow_password', default='', required=True, help='SNOW API Password')

    args = parser.parse_args()
    # Make it a dictionary so we can simulate it in lambda
    args = vars(args)
    return args


def process_sqs(source_sqs_name, aws_region_sqs, args):
    '''Takes the messages from the SQS queue and processes it'''
    sqs_resource = boto3.resource('sqs', region_name=aws_region_sqs)

    queue = sqs_resource.get_queue_by_name(QueueName=source_sqs_name)

    # During dev work we hide messages for 30 seconds. To not end up in an
    # endless loop lets check the count and exit when done.
    logging.info("SQS queue length visible: %s, not visible: %s" % (queue.attributes['ApproximateNumberOfMessages'], queue.attributes['ApproximateNumberOfMessagesNotVisible']))
    while int(queue.attributes['ApproximateNumberOfMessages']) > 0:
        for raw_message in queue.receive_messages(MaxNumberOfMessages=10,
                                                  VisibilityTimeout=30,
                                                  WaitTimeSeconds=5):
            message = json.loads(raw_message.body)
            process_single_message(message, args)

            # Cleanup everything we skip, saves processing time on multiple runs
            if message['messageType'] in SKIP_MESSAGE_TYPES:
                raw_message.delete()
                logging.debug("Deleted message from SQS queue: %s" % message['messageType'])
                continue

            if 'configurationItemSummary' in message and message['configurationItemSummary']['resourceType'] not in ACCEPT_RESOURCES:
                raw_message.delete()
                logging.debug("Deleted message from SQS queue: %s" % message['configurationItemSummary']['resourceType'])
                continue

            if 'configurationItem' in message and message['configurationItem']['resourceType'] not in ACCEPT_RESOURCES:
                raw_message.delete()
                logging.debug("Deleted message from SQS queue: %s" % message['configurationItem']['resourceType'])
                continue


def _logger_config(args):
    FORMAT = "[%(levelname)8s:%(filename)25s:%(lineno)4s - %(funcName)45s()] %(message)s"
    logger = logging.getLogger()
    logger_handler = logger.handlers[0]
    logger_handler.setFormatter(logging.Formatter(FORMAT))
    if 'debug' in args:
        logger.setLevel(logging.DEBUG)

        if 'LAMBDA_TASK_ROOT' not in os.environ:
            logger.getLogger('boto3').setLevel(logging.CRITICAL)
            logger.getLogger('botocore').setLevel(logging.CRITICAL)
            logger.getLogger('botocore.credentials').setLevel(logging.CRITICAL)
            logger.getLogger('urllib3').setLevel(logging.CRITICAL)
            logger.getLogger('s3transfer').setLevel(logging.CRITICAL)
    else:
        logger.setLevel(logging.INFO)


if __name__ == "__main__":
    args = parse_arguments()
    _logger_config(args)

    process_sqs(args['source_sqs_name'], args['aws_region_sqs'], args)

