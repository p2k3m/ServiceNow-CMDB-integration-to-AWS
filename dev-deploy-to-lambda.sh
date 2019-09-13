#!/bin/bash

set -e
set -u

#
# This script is just for development work of the lambda deployment
#

# Define some variables in terraform
export TF_VAR_snow_user="$SNOW_USER"
export TF_VAR_snow_password="$SNOW_PASSWORD"
export TF_VAR_snow_hostname="orgs.service-now.com"

echo -e "\n#\n#\n#\n# TF Init\n#\n#\n#"
cd tf && terraform init

#echo -e "\n#\n#\n#\n# TF Destroy?\n#\n#\n#"
#read -p "Run terraform destroy? " yn
#if [[ "$yn" == y* ]] || [[ "$yn" == Y* ]]; then
#   terraform destroy
#fi

echo -e "\n#\n#\n#\n# TF Apply\n#\n#\n#"
terraform apply -auto-approve
