
import boto3
from botocore.exceptions import ClientError

import json
import os
import time
import datetime
from dateutil import tz

from lib.account import *
from lib.common import *

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)

RESOURCE_PATH = "secretsmanager"

def lambda_handler(event, context):
    logger.debug("Received event: " + json.dumps(event, sort_keys=True))
    message = json.loads(event['Records'][0]['Sns']['Message'])
    logger.info("Received message: " + json.dumps(message, sort_keys=True))

    try:
        target_account = AWSAccount(message['account_id'])
        for r in target_account.get_regions():
            discover_secrets(target_account, r)

    except AssumeRoleError as e:
        logger.error("Unable to assume role into account {}({})".format(target_account.account_name, target_account.account_id))
        return()
    except ClientError as e:
        logger.error("AWS Error getting info for {}: {}".format(target_account.account_name, e))
        return()
    except Exception as e:
        logger.error("{}\nMessage: {}\nContext: {}".format(e, message, vars(context)))
        raise

def discover_secrets(target_account, region):
    '''Iterate across all regions to discover Cloudsecrets'''

    secrets = []
    client = target_account.get_client('secretsmanager', region=region)
    response = client.list_secrets()
    while 'NextToken' in response:  # Gotta Catch 'em all!
        secrets += response['SecretList']
        response = client.list_secrets(NextToken=response['NextToken'])
    secrets += response['SecretList']

    for s in secrets:
        process_secret(client, s, target_account, region)

def process_secret(client, secret, target_account, region):

    resource_name = "{}-{}-{}".format(target_account.account_id, region, secret['Name'].replace("/", "-"))

    response = client.get_resource_policy(SecretId=secret['ARN'])
    if 'ResourcePolicy' in response:
        secret['ResourcePolicy']    = json.loads(response['ResourcePolicy'])
    if 'Tags' in secret:
        secret['Tags']              = parse_tags(secret['Tags'])

    secret['resource_type']     = "secretsmanager"
    secret['region']            = region
    secret['account_id']        = target_account.account_id
    secret['account_name']      = target_account.account_name
    secret['last_seen']         = str(datetime.datetime.now(tz.gettz('US/Eastern')))
    save_resource_to_s3(RESOURCE_PATH, resource_name, secret)


