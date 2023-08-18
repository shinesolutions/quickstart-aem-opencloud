import logging
import re
import os
import tempfile
import boto3
from botocore.exceptions import ClientError
from crhelper import CfnResource
from ruamel.yaml import YAML

# Create Temp file
file_name = 'ami.yaml'
tmpdir = tempfile.mkdtemp()
saved_umask = os.umask(0o077)
packer_config_path = os.path.join(tmpdir, file_name)

ssm = boto3.client('ssm')
s3 = boto3.resource('s3')
s3_client = boto3.client('s3')
secretsmanager = boto3.client('secretsmanager')
helper = CfnResource()
yaml=YAML(typ='safe')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_s3_object_content(s3_bucket, s3_key):
    try:
        logger.info(f'S3 Download source_bucket:{s3_bucket}\nkey: {s3_key}\n')
        return s3.Object(s3_bucket, s3_key).get()["Body"].read().decode("utf-8")
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']

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

def get_secret_string(secret_name):
    try:
        logger.info(f'Get Secret {secret_name}')
        response = secretsmanager.get_secret_value(
            SecretId=secret_name
        )
        return response['SecretString']
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']

def write_parameter(parameter_name, param_value):
    try:
        logger.info(f'Put AEM License to SSM ParameterStore\n SSM Parameter Name: {parameter_name}')
        response = ssm.put_parameter(
            Name=parameter_name,
            Value=param_value,
            Type='SecureString'
        )
        return response
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']

def del_ssm_param(parameter_name):
    try:
        logger.info(f'Delete AEM License from SSM ParameterStore\n SSM Parameter Name: {parameter_name}')
        response = ssm.delete_parameter(
            Name=parameter_name
        )
        return response
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        if e.response['Error']['Code'] == 'ParameterNotFound':
            response = "ParameterNotFound : "+parameter_name
            return response
        else:
            return e.response['Error']

def read_file(file_path):
    logger.info('Read Packer-AEM Configuration from filesystem')
    try:
        with open (file_path, 'r') as file_stream:
            return file_stream.read()
    except Exception as e:
        logger.error('Error while reading file from filesystem', exc_info=True)
        return e

def write_yaml_file(dest_file_path, yaml_content):
    logger.info('Write Packer-AEM Configuration to filesystem')
    try:
        with open(dest_file_path, 'w', encoding='utf-8') as save_file:
            yaml.default_flow_style = False
            yaml.dump(yaml_content, save_file)
    except Exception as e:
        logger.error('Error while writing file to filesystem', exc_info=True)
        return e

@helper.create
def create(event, _):
    aem_dispatcher_version = event['ResourceProperties']['AemDispatcherVersion']
    aem_profile = event['ResourceProperties']['AemInstallationProfile']
    aem_healthcheck_content_version = event['ResourceProperties']['AemHealthcheckContentVersion']
    aem_keystore_password_sm_id = event['ResourceProperties']['AemKeystorePasswordSmId']
    aem_license = event['ResourceProperties']['AemLicenseSSMParameter']
    java_jdk_version = event['ResourceProperties']['JavaJdkVersion']
    ssl_certificate_acm_arn = event['ResourceProperties']['SslCertificateAcmArn']
    ssl_private_key_sm_arn = event['ResourceProperties']['SslPrivateKeySmArn']
    timezone = event['ResourceProperties']['Timezone']
    region = event['ResourceProperties']['Region']
    s3_source_bucket = event['ResourceProperties']['S3SourceBucket']
    s3_source_key = event['ResourceProperties']['S3SourceKey']
    s3_data_bucket = event['ResourceProperties']['S3DataBucket']
    s3_installation_bucket = event['ResourceProperties']['S3InstallBucketName']
    aoc_stack_prefix = event['ResourceProperties']['AOCStackPrefix']
    s3_installation_source_raw = event['ResourceProperties']['S3InstallKeyPrefix']
    s3_installation_source = re.sub('/$', '', s3_installation_source_raw)
    aem_keystore_password = get_secret_string(aem_keystore_password_sm_id)

    timezone_region = timezone.split('/')[0]
    timezone_locality = timezone.split('/')[1]
    jdk_version = java_jdk_version.split('u')[0]
    jdk_version_update = java_jdk_version.split('u')[1]

    aem_license_body =  get_s3_object_content(s3_installation_bucket, s3_installation_source + '/license.properties')

    write_parameter(aem_license, aem_license_body)

    s3_download(packer_config_path, s3_source_bucket, s3_source_key + 'scripts/' + file_name)

    file_content = read_file(packer_config_path)
    local_yaml = yaml.load(file_content)

    local_yaml['aem_curator::install_publish::aem_profile'] = aem_profile
    local_yaml['aem_curator::install_author::aem_profile'] = aem_profile
    local_yaml['aem_curator::install_author::aem_keystore_password'] = aem_keystore_password
    local_yaml['aem_curator::install_publish::aem_keystore_password'] = aem_keystore_password
    local_yaml['aem_curator::install_dispatcher::apache_module_tarball'] = "dispatcher-apache2.4-linux-x86_64-ssl1.1-" + aem_dispatcher_version + ".tar.gz"
    local_yaml['aem_curator::install_dispatcher::apache_module_filename'] = "dispatcher-apache2.4-" + aem_dispatcher_version + ".so"
    local_yaml['aem_curator::install_java::jdk_filename'] = "jdk-" + java_jdk_version + "-linux-x64.rpm"
    local_yaml['aem_curator::install_java::jdk_version'] = jdk_version
    local_yaml['aem_curator::install_java::jdk_version_update'] = jdk_version_update
    local_yaml['aem_curator::install_author::aem_artifacts_base'] = "s3://" + s3_installation_bucket + "/" + s3_installation_source
    local_yaml['aem_curator::install_publish::aem_artifacts_base'] = "s3://" + s3_installation_bucket + "/" + s3_installation_source
    local_yaml['aem_curator::install_dispatcher::apache_module_base_url'] = "s3://" + s3_installation_bucket + "/" + s3_installation_source
    local_yaml['aem_curator::install_java::jdk_base_url'] = "s3://" + s3_installation_bucket + "/" + s3_installation_source
    local_yaml['aem_curator::install_author::aem_healthcheck_source'] = "s3://" + s3_data_bucket + "/" + aoc_stack_prefix + '/aem-healthcheck-content-' + aem_healthcheck_content_version + '.zip'
    local_yaml['aem_curator::install_publish::aem_healthcheck_source'] = "s3://" + s3_data_bucket + "/" + aoc_stack_prefix + '/aem-healthcheck-content-' + aem_healthcheck_content_version + '.zip'
    local_yaml['cloudwatchlogs::region'] = region
    local_yaml['config::license::region'] = region
    local_yaml['config::certs::region'] = region
    local_yaml['config::license::aem_profile'] = aem_profile
    local_yaml['config::license::aem_license'] = re.sub('^/', '', aem_license)
    local_yaml['config::certs::certificate_arn'] = ssl_certificate_acm_arn
    local_yaml['config::certs::certificate_key_arn'] = ssl_private_key_sm_arn
    local_yaml['timezone::region'] = timezone_region
    local_yaml['timezone::locality'] = timezone_locality

    write_yaml_file(packer_config_path, local_yaml)

    s3_upload(packer_config_path, s3_data_bucket, aoc_stack_prefix + '/ami.yaml')

    # Remove created temp file
    os.remove(packer_config_path)
    os.umask(saved_umask)
    os.rmdir(tmpdir)

@helper.update
def no_op(_, __):
    pass
@helper.delete
def delete(event, __):
    aem_license = event['ResourceProperties']['AemLicenseSSMParameter']
    del_ssm_param(aem_license)

def handler(event, context):
    logger.debug(event)
    helper(event, context)
