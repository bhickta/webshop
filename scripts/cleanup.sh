#!/bin/bash
set -e

if [[ "$DEPLOYMENT_GROUP_NAME" == "Rapl-Prod-Group" ]]; then
    ARTIFACTS_DIR="/home/frappe/codedeploy-artifacts/webshop-prod"
elif [[ "$DEPLOYMENT_GROUP_NAME" == "Rapl-Dev-Group" ]]; then
    ARTIFACTS_DIR="/home/frappe/codedeploy-artifacts/webshop-dev"
else
    echo "ERROR: Unknown DEPLOYMENT_GROUP_NAME: $DEPLOYMENT_GROUP_NAME"
    exit 1
fi

# The live app stays in place until AfterInstall has a complete staged copy.
rm -rf /tmp/codedeploy-webshop
if [ -d "$ARTIFACTS_DIR" ]; then
    rm -rf "$ARTIFACTS_DIR"
fi

echo "Cleanup complete."
