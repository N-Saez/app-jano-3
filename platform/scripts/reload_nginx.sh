#!/bin/bash
# Valida y recarga Nginx sin downtime.
# Llamado por deployer.py via sudo.
set -e
nginx -t
systemctl reload nginx
