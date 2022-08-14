#!/usr/bin/env bash
set -o nounset
set -o errexit

PATH=/opt/puppetlabs/bin:/opt/puppetlabs/puppet/bin:${PATH}

if [ $# -ne 2 ]; then
    echo $0: usage: install_aem_opencloud.sh "<component_name> <aws_region>"
    exit 1
fi

# Translate puppet detailed exit codes to basic convention 0 to indicate success.
# More info on Puppet --detailed-exitcodes https://puppet.com/docs/puppet/5.3/man/agent.html
translate_puppet_exit_code() {
  exit_code="$1"

  # 0 (success) and 2 (success with changes) are considered as success.
  # Everything else is considered to be a failure.
  if [ "$exit_code" -eq 0 ] || [ "$exit_code" -eq 2 ]; then
    exit_code=0
  else
    exit "$exit_code"
  fi

  return "$exit_code"
}

COMPONENT=$1
AWS_REGION=$2

PUPPET_MAJOR_VERSION=7
PUPPET_MINOR_VERSION=9
PUPPET_PATCH_VERSION=0
PUPPET_AGENT_VERSION="${PUPPET_MAJOR_VERSION}.${PUPPET_MINOR_VERSION}.${PUPPET_PATCH_VERSION}"
ARCH_TYPE=x86_64
OS_TYPE=el
OS_VERSION=7

TMP_DIR=/tmp/shinesolutions

export AWS_DEFAULT_REGION="${AWS_REGION}"
echo "AWS Region: ${AWS_DEFAULT_REGION}"

amazon-linux-extras enable tomcat8.5

yum -y upgrade

yum -y install "https://yum.puppetlabs.com/puppet${PUPPET_MAJOR_VERSION}/${OS_TYPE}/${OS_VERSION}/${ARCH_TYPE}/puppet-agent-${PUPPET_AGENT_VERSION}-1.${OS_TYPE}${OS_VERSION}.${ARCH_TYPE}.rpm"

yum-config-manager --enable rhui-REGION-rhel-server-optional
yum-config-manager --enable rhui-REGION-rhel-server-extras
yum-config-manager --enable "rhel-${OS_VERSION}-server-rhui-optional-rpms"

echo "Preparing AEM OpenCloud installation"

mkdir -p $TMP_DIR/packer-aem

tar xzf $TMP_DIR/packer-aem.tar.gz -C $TMP_DIR/packer-aem/

cd $TMP_DIR/packer-aem

cp $TMP_DIR/local.yaml $TMP_DIR/packer-aem/conf/puppet/hieradata/local.yaml
cp $TMP_DIR/hiera.yaml $TMP_DIR/packer-aem/conf/puppet/hiera.yaml
cp $TMP_DIR/hiera3.yaml $TMP_DIR/packer-aem/conf/puppet/hiera3.yaml
cp $TMP_DIR/hiera3.yaml $TMP_DIR/packer-aem/hiera3.yaml

#
# Fix for the dispatcher component to support Instance Types with NVME Devices
#
if [ ${COMPONENT} = "dispatcher" ]; then
  rm -f $TMP_DIR/packer-aem/test/inspec/dispatcher_spec.rb
  cp $TMP_DIR/dispatcher_spec.rb $TMP_DIR/packer-aem/test/inspec/dispatcher_spec.rb
fi

set +o errexit

echo "Finished preparing AEM OpenCloud installation"

echo "Starting AEM OpenCloud installation"

export FACTER_component=$COMPONENT && \
  export FACTER_platform_type='aws' && \
  export FACTER_aws_region=$AWS_REGION && \
  /opt/puppetlabs/bin/puppet apply \
  --detailed-exitcodes \
  --verbose \
  --modulepath="${TMP_DIR}/packer-aem/modules:${TMP_DIR}/packer-aem/provisioners/puppet/modules" \
  $TMP_DIR/packer-aem/provisioners/puppet/manifests/config.pp
translate_puppet_exit_code "$?"

export FACTER_component=$COMPONENT && \
  export FACTER_platform_type='aws' && \
  export FACTER_aws_region=$AWS_REGION && \
  /opt/puppetlabs/bin/puppet apply \
  --detailed-exitcodes  \
  --verbose \
  --modulepath="${TMP_DIR}/packer-aem/modules:${TMP_DIR}/packer-aem/provisioners/puppet/modules" \
  --hiera_config="${TMP_DIR}/packer-aem/conf/puppet/hiera.yaml" \
  "${TMP_DIR}/packer-aem/provisioners/puppet/manifests/${COMPONENT}.pp"
translate_puppet_exit_code "$?"

set -o errexit

echo "Finished AEM OpenCloud installation"

echo "Start verifying AEM OpenCloud installation"

cd $TMP_DIR/packer-aem/test/inspec

export FACTER_packer_build_name=$COMPONENT && \
  export FACTER_packer_staging_dir="${TMP_DIR}/packer-aem/conf/puppet" && \
  export HOME=/root && \
  /opt/puppetlabs/puppet/bin/inspec exec base_spec.rb

export FACTER_packer_build_name=$COMPONENT && \
  export FACTER_packer_staging_dir="${TMP_DIR}/packer-aem/conf/puppet" && \
  export HOME=/root && \
  /opt/puppetlabs/puppet/bin/inspec exec aem_base_spec.rb

export FACTER_packer_build_name=$COMPONENT && \
  export FACTER_packer_staging_dir="${TMP_DIR}/packer-aem/conf/puppet" && \
  export HOME=/root && \
 /opt/puppetlabs/puppet/bin/inspec exec "${COMPONENT}_spec.rb"

echo "Successfully verified AEM OpenCloud installation."
