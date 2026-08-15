#!/bin/bash
set -e

export PATH="/home/frappe/.nvm/versions/node/v24.11.1/bin:$PATH"

APP="webshop"

log() { echo "--- $(date '+%Y-%m-%d %H:%M:%S') | $1 ---"; }

if [[ "$DEPLOYMENT_GROUP_NAME" == "Rapl-Prod-Group" ]]; then
    BENCH_DIR="/home/frappe/prod-bench"
    SITE="prodrapl"
    ARTIFACTS="/home/frappe/codedeploy-artifacts/webshop-prod"
elif [[ "$DEPLOYMENT_GROUP_NAME" == "Rapl-Dev-Group" ]]; then
    BENCH_DIR="/home/frappe/dev-bench"
    SITE="devrapl"
    ARTIFACTS="/home/frappe/codedeploy-artifacts/webshop-dev"
else
    log "ERROR: Unknown DEPLOYMENT_GROUP_NAME: '$DEPLOYMENT_GROUP_NAME'."
    exit 1
fi

SKIP_BUILD="false"
SKIP_MIGRATE="false"
SKIP_RESTART="false"

log "Staging new artifacts..."
if [ ! -d "/tmp/codedeploy-webshop" ]; then
    log "ERROR: /tmp/codedeploy-webshop not found."
    exit 1
fi

mkdir -p "$ARTIFACTS"
cp -a /tmp/codedeploy-webshop/. "$ARTIFACTS/"
rm -rf /tmp/codedeploy-webshop

CONFIG_FILE="$ARTIFACTS/.deploy_config"
if [ -f "$CONFIG_FILE" ]; then
    log "Loading configuration from $CONFIG_FILE"
    source "$CONFIG_FILE"
fi

log "Deploying $APP to $BENCH_DIR"
log "Flags: SKIP_BUILD=$SKIP_BUILD | SKIP_MIGRATE=$SKIP_MIGRATE | SKIP_RESTART=$SKIP_RESTART"

rm -rf "$BENCH_DIR/apps/$APP"
cp -r "$ARTIFACTS" "$BENCH_DIR/apps/$APP"
chown -R frappe:frappe "$BENCH_DIR/apps/$APP"

sudo -i -u frappe bash <<EOF
set -e
export NVM_DIR="\$HOME/.nvm"
[ -s "\$NVM_DIR/nvm.sh" ] && \. "\$NVM_DIR/nvm.sh"

cd $BENCH_DIR/apps/$APP

log() { echo "--- \$(date '+%Y-%m-%d %H:%M:%S') | \$1 ---"; }

if [ ! -d ".git" ]; then
    log "Initializing deployment artifact repository..."
    git init
    git config user.email "deploy@bot.com"
    git config user.name "DeployBot"
    git add .
    git commit -m "Deploy artifact"
fi

cd $BENCH_DIR

log "Installing Python dependencies..."
./env/bin/pip install -e apps/$APP

if ! grep -q "^$APP$" sites/apps.txt; then
    log "Adding $APP to sites/apps.txt..."
    echo "$APP" >> sites/apps.txt
fi

log "Installing Node dependencies..."
bench setup requirements --node

if [ "$SKIP_BUILD" != "true" ]; then
    log "Building assets..."
    bench build --app $APP
else
    log "Skipping build"
fi

if [ "$SKIP_MIGRATE" != "true" ]; then
    log "Clearing cache and migrating $SITE..."
    bench --site $SITE clear-cache
    bench --site $SITE migrate
else
    log "Skipping migrate"
fi

if [ "$SKIP_RESTART" != "true" ]; then
    log "Restarting bench..."
    bench restart
else
    log "Skipping restart"
fi
EOF

log "Deployment complete."
