#  Copyright 2016 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
#  This file is licensed to you under the AWS Customer Agreement (the "License").
#  You may not use this file except in compliance with the License.
#  A copy of the License is located at http://aws.amazon.com/agreement/ .
#  This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied.
#  See the License for the specific language governing permissions and limitations under the License.

# parameters needed:
# CertificateSSMPath, PrivateKeySecretsManagerName
import random
import boto3
import logging
from botocore.exceptions import ClientError
from OpenSSL import crypto
from crhelper import CfnResource

# Create clients
acm = boto3.client('acm')
secretsmanager = boto3.client('secretsmanager')
ssm = boto3.client('ssm')
helper = CfnResource()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def create_self_signed_cert(fqdn):
    # Create CA
    logger.info('Create Private CA')
    ca_key = crypto.PKey()
    ca_key.generate_key(crypto.TYPE_RSA, 2048)
    ca_cert = crypto.X509()
    ca_cert.set_version(2)
    ca_cert.set_serial_number(random.randrange(100000))
    ca_subj = ca_cert.get_subject()
    ca_subj.C = "AU"
    ca_subj.ST = "Victoria"
    ca_subj.L = "Melbourne"
    ca_subj.O = "ShineSolutions"
    ca_subj.OU = "AEM OpenCloud"
    ca_subj.CN = "Quickstart AEM OpenCloud CA 1"
    ca_cert.add_extensions([
        crypto.X509Extension(b"subjectKeyIdentifier", False, b"hash", subject=ca_cert),
    ])
    ca_cert.add_extensions([
        crypto.X509Extension(b"authorityKeyIdentifier", False, b"keyid:always", issuer=ca_cert),
    ])
    ca_cert.add_extensions([
        crypto.X509Extension(b"basicConstraints", False, b"CA:TRUE"),
        crypto.X509Extension(b"keyUsage", False, b"keyCertSign, cRLSign"),
    ])
    ca_cert.set_issuer(ca_subj)
    ca_cert.set_pubkey(ca_key)
    ca_cert.sign(ca_key, 'sha256')
    ca_cert.gmtime_adj_notBefore(0)
    ca_cert.gmtime_adj_notAfter(10*365*24*60*60)
    ca_certifictate_pem = crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert).decode('utf-8')
    logger.info('Private CA successfully created')
    # Create Certificate
    logger.info('Create Self-Signed Certificate')
    client_key = crypto.PKey()
    client_key.generate_key(crypto.TYPE_RSA, 2048)
    client_cert = crypto.X509()
    client_cert.set_version(2)
    client_cert.set_serial_number(random.randrange(100000))
    client_subj = client_cert.get_subject()
    client_subj.C = "AU"
    client_subj.ST = "Victoria"
    client_subj.L = "Melbourne"
    client_subj.O = "Shinesolutions"
    client_subj.OU = "AEM OpenCloud"
    client_subj.CN = "localhost"
    client_cert.add_extensions([
        crypto.X509Extension(b"basicConstraints", False, b"CA:FALSE"),
        crypto.X509Extension(b"subjectKeyIdentifier", False, b"hash", subject=client_cert),
    ])
    client_cert.add_extensions([
        crypto.X509Extension(b"authorityKeyIdentifier", False, b"keyid:always", issuer=ca_cert),
        crypto.X509Extension(b"extendedKeyUsage", False, b"serverAuth"),
        crypto.X509Extension(b"keyUsage", False, b"digitalSignature"),
    ])
    client_cert.add_extensions([
        crypto.X509Extension(b'subjectAltName', False,
            ','.join([
                'DNS:%s' % fqdn,
                'DNS:*.%s' % fqdn,
                'DNS:localhost',
                'DNS:*.localhost'
    ]).encode())])
    client_cert.set_issuer(ca_subj)
    client_cert.set_pubkey(client_key)
    client_cert.gmtime_adj_notBefore(0)
    client_cert.gmtime_adj_notAfter(9*365*24*60*60)
    client_cert.sign(ca_key, 'sha256')
    certifictate_pem = crypto.dump_certificate(crypto.FILETYPE_PEM, client_cert).decode('utf-8')
    private_key_pem = crypto.dump_privatekey(crypto.FILETYPE_PEM, client_key).decode('utf-8')
    response = {
        'certificate': certifictate_pem,
        'private_key': private_key_pem,
        'certificate_chain': ca_certifictate_pem
    }
    return response

def delete_sm_parameter(secret_name):
    try:
        logger.info(f'Delete Secret {secret_name}')
        response = secretsmanager.delete_secret(
            SecretId=secret_name
        )
        return response
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            response = "ResourceNotFound : "+secret_name
            return response
        else:
            return e.response['Error']

def del_acm_cert(cert_arn):
    try:
        logger.info(f'Delete Certificate {cert_arn}')
        response = acm.delete_certificate(
            CertificateArn=cert_arn
        )
        return response
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            response = e.response['Error']['Message']
            return response
        else:
            return e.response['Error']
def del_ssm_param(parameter_name):
    try:
        logger.info(f'Delete SSM Parameter {parameter_name}')
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
def import_acm(certificate, private_key, certificate_chain):
    try:
        logger.info('Import Private Certificate to ACM')
        response = acm.import_certificate(
            Certificate=certificate,
            PrivateKey=private_key,
            CertificateChain=certificate_chain,
            Tags=[
                {
                    'Key': 'Name',
                    'Value': 'Quickstart AEM OpenCloud'
                }
            ]
        )
        return response
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']
def get_param_value(parameter_name):
    try:
        logger.info(f'Get SSM Parameter {parameter_name}')
        response = ssm.get_parameter(
            Name=parameter_name
        )
        return response['Parameter']
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        if e.response['Error']['Code'] == 'ParameterNotFound':
            response = "ParameterNotFound : "+parameter_name
            return response
        else:
            return e.response['Error']
def write_parameter(param_name, param_value):
    try:
        logger.info(f'Put SSM Parameter {param_name}')
        response = ssm.put_parameter(
            Name=param_name,
            Value=param_value,
            Type='String'
        )
        return response
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']
def write_sm_parameter(secret_name, secret_string):
    try:
        logger.info(f'Save Private Key to SecretsManager {secret_name}')
        response = secretsmanager.create_secret(
            Name=secret_name,
            SecretString=secret_string
        )
        return response
    except ClientError as e:
        logger.error('Unhandled exception', exc_info=True)
        return e.response['Error']
@helper.create
def generate_upload(event, _):
    acm_ssm_path = event['ResourceProperties']['CertificateSSMPath']
    ssl_cert_fqdn = event['ResourceProperties']['SSLCertFQDN']
    private_key_sm_name = event['ResourceProperties']['PrivateKeySecretsManagerName']
    selfsigned_cert = create_self_signed_cert(ssl_cert_fqdn)

    certificate_pem = selfsigned_cert['certificate']
    private_key_pem = selfsigned_cert['private_key']
    certificate_chain_pem = selfsigned_cert['certificate_chain']

    import_acm_response = import_acm(certificate_pem, private_key_pem, certificate_chain_pem)
    certificate_arn = import_acm_response['CertificateArn']
    write_parameter(acm_ssm_path, certificate_arn)
    sm_import = write_sm_parameter(private_key_sm_name, private_key_pem)
    helper.Data['CertificateArn'] = certificate_arn
    helper.Data['PrivateKeyArn'] = sm_import['ARN']
@helper.update
def no_op(_, __):
    pass
@helper.delete
def remove_resources(event, __):
    acm_ssm_path = event['ResourceProperties']['CertificateSSMPath']
    private_key_sm_name = event['ResourceProperties']['PrivateKeySecretsManagerName']
    acm_parameter_response = get_param_value(acm_ssm_path)
    acm_ssm_name = acm_parameter_response['Name']
    acm_arn = acm_parameter_response['Value']
    del_acm_cert(acm_arn)
    del_ssm_param(acm_ssm_name)
    delete_sm_parameter(private_key_sm_name)
def handler(event, context):
    helper(event, context)
