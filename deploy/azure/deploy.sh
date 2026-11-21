#!/usr/bin/env bash
# Đưa một image đã có trong registry lên bản Azure: app `api`, job chuyển mã, job bảo trì.
# Dùng cho cả triển khai (tag = commit vừa build) và rollback (tag = commit cũ còn tốt):
#   REGISTRY=<tên registry> bash deploy/azure/deploy.sh <commit SHA đầy đủ>
# Cần phiên `az login` (trong GitHub Actions: azure/login bằng OIDC, identity `deploy`).
# Nếu bản mới không khoẻ sau thời gian chờ, script tự đưa image cũ trở lại và kết thúc với mã lỗi.
set -euo pipefail

tag="${1:?usage: deploy.sh <image tag>}"
: "${REGISTRY:?set REGISTRY to the registry name}"
group="${RESOURCE_GROUP:-videoportal-rg}"
app="${API_APP:-videoportal-api}"
transcode="${TRANSCODE_JOB:-videoportal-transcode}"
maintenance="${MAINTENANCE_JOB:-videoportal-maintenance}"

# Tag là SHA của commit: chỉ chữ số hex, nên giá trị nhập tay ở workflow rollback không chen được lệnh nào.
if ! [[ "$tag" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::image tag must be a full 40-character commit SHA"
  exit 2
fi
az config set extension.use_dynamic_install=yes_without_prompt --only-show-errors

api_image="$REGISTRY.azurecr.io/video-portal-api:$tag"
worker_image="$REGISTRY.azurecr.io/video-portal-worker:$tag"
for name in api worker; do
  az acr repository show --name "$REGISTRY" --image "video-portal-$name:$tag" --output none
done

set_images() {  # $1 = image api, $2 = image worker
  az containerapp update --name "$app" --resource-group "$group" --image "$1" --output none
  az containerapp job update --name "$transcode" --resource-group "$group" --image "$2" --output none
  az containerapp job update --name "$maintenance" --resource-group "$group" --image "$1" --output none
}

previous_api=$(az containerapp show --name "$app" --resource-group "$group" --query "properties.template.containers[0].image" --output tsv)
previous_worker=$(az containerapp job show --name "$transcode" --resource-group "$group" --query "properties.template.containers[0].image" --output tsv)
previous_revision=$(az containerapp show --name "$app" --resource-group "$group" --query "properties.latestReadyRevisionName" --output tsv)
fqdn=$(az containerapp show --name "$app" --resource-group "$group" --query "properties.configuration.ingress.fqdn" --output tsv)
echo "previous: ${previous_api##*:} (revision $previous_revision)"
echo "target:   $tag"

set_images "$api_image" "$worker_image"

# Chờ tới khi revision sẵn sàng mới nhất chạy đúng image mới và /health báo database ok (tối đa 5 phút).
healthy=""
for attempt in $(seq 1 30); do
  revision=$(az containerapp show --name "$app" --resource-group "$group" --query "properties.latestReadyRevisionName" --output tsv)
  running=$(az containerapp revision show --name "$app" --resource-group "$group" --revision "$revision" --query "properties.template.containers[0].image" --output tsv)
  health=$(curl --silent --show-error --max-time 10 "https://$fqdn/health" || true)
  if [ "$running" = "$api_image" ] && [[ "$health" == *'"database":"ok"'* ]]; then
    healthy="yes"
    break
  fi
  echo "waiting ($attempt/30): ready revision $revision"
  sleep 10
done

summary="${GITHUB_STEP_SUMMARY:-/dev/null}"
if [ -z "$healthy" ]; then
  echo "::error::new revision did not become healthy; restoring ${previous_api##*:}"
  set_images "$previous_api" "$previous_worker"
  echo "Deploy of \`$tag\` FAILED; restored \`${previous_api##*:}\`" >> "$summary"
  exit 1
fi
echo "healthy: revision $revision serves $tag"
{
  echo "Deployed image tag \`$tag\`"
  echo "- previous image tag: \`${previous_api##*:}\` (revision \`$previous_revision\`)"
  echo "- new ready revision: \`$revision\`"
  echo "- health: \`$health\`"
} >> "$summary"
