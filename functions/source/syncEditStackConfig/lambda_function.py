import logging
import os
import tempfile
import boto3
from botocore.exceptions import ClientError
from crhelper import CfnResource
from ruamel.yaml import YAML

file_name = 'local.yaml'
tmpdir = tempfile.mkdtemp()
saved_umask = os.umask(0o077)
stack_config_path = os.path.join(tmpdir, file_name)

s3_client = boto3.client('s3')
helper = CfnResource()
yaml=YAML(typ='safe')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def s3_download(file_name, bucket, key):
    try:
        logger.info(f'S3 Download source_bucket:{bucket}\nkey: {key}\n')
        s3_client.download_file(bucket, key, file_name)
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']

def s3_upload(file_name, bucket, key):
    try:
        logger.info(f'S3 Upload destination_bucket:{bucket}\nkey: {key}\n')
        s3_client.upload_file(file_name, bucket, key)
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']

def read_file(file_path):
    logger.info('Read configuration file from filesystem')
    try:
        with open (file_path, 'r') as file_stream:
            return file_stream.read()
    except Exception as e:
        logger.error('Error while reading configuration from filesystem', exc_info=True)
        return e

def write_yaml_file(dest_file_path, yaml_content):
    logger.info('Write configuration to filesystem')
    try:
        with open(dest_file_path, 'w', encoding='utf-8') as save_file:
            yaml.default_flow_style = False
            yaml.dump(yaml_content, save_file)
    except Exception as e:
        logger.error('Error while writing configuration to filesystem', exc_info=True)
        return e

@helper.create
def create(event, _):
    region = event['ResourceProperties']['Region']
    aem_oak_run_version = event['ResourceProperties']['AemOakRunVersion']
    s3_source_bucket = event['ResourceProperties']['S3SourceBucket']
    s3_source_key = event['ResourceProperties']['S3SourceKey']
    s3_data_bucket = event['ResourceProperties']['S3DataBucket']
    aoc_stack_prefix = event['ResourceProperties']['AOCStackPrefix']

    s3_download(stack_config_path, s3_source_bucket, s3_source_key + 'scripts/' + file_name)

    file_content = read_file(stack_config_path)
    local_yaml = yaml.load(file_content)

    local_yaml['common::aws_region'] = region
    local_yaml['aem_curator::config_aem_tools::oak_run_version'] = aem_oak_run_version

    write_yaml_file(stack_config_path, local_yaml)

    s3_upload(stack_config_path, s3_data_bucket, aoc_stack_prefix + '/data/local.yaml')

    # Remove created temp file
    os.remove(stack_config_path)
    os.umask(saved_umask)
    os.rmdir(tmpdir)

@helper.update
def no_op(_, __):
    pass
@helper.delete
def no_op(_, __):
    pass

def handler(event, context):
    logger.debug(event)
    helper(event, context)
